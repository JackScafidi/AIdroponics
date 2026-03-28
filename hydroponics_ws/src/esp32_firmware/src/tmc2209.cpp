/*
 * tmc2209.cpp  –  TMC2209 single-wire UART driver
 *
 * Packet format (TMC2209 datasheet §5.1):
 *
 *  Write datagram  (8 bytes from master):
 *    [0]  sync + reserved  = 0x05
 *    [1]  slave address    = 0x00–0x03
 *    [2]  register address | 0x80 (write bit)
 *    [3–6] data MSB first
 *    [7]  CRC8
 *
 *  Read request    (4 bytes from master):
 *    [0]  0x05
 *    [1]  slave address
 *    [2]  register address  (no write bit)
 *    [3]  CRC8
 *
 *  Read reply      (8 bytes from slave):
 *    [0]  0x05
 *    [1]  0xFF  (reply address)
 *    [2]  register address
 *    [3–6] data MSB first
 *    [7]  CRC8
 *
 * Because we use a single-wire UART the TX echo appears on RX;
 * we discard those bytes before reading the slave reply.
 */

#include "tmc2209.h"
#include <Arduino.h>
#include <HardwareSerial.h>

// Use UART2 on ESP32
static HardwareSerial &s_tmc_serial = Serial2;

// ── CRC8 (polynomial 0x07) ───────────────────────────────────────────────────
static uint8_t crc8(const uint8_t *data, size_t len)
{
    uint8_t crc = 0;
    for (size_t i = 0; i < len; i++) {
        uint8_t b = data[i];
        for (int j = 0; j < 8; j++) {
            if ((crc ^ b) & 0x80) {
                crc = (crc << 1) ^ 0x07;
            } else {
                crc <<= 1;
            }
            b <<= 1;
        }
    }
    return crc;
}

// ── Low-level send / receive ─────────────────────────────────────────────────
static void flush_rx(void)
{
    // Drain any stale bytes from the RX buffer
    uint32_t t0 = millis();
    while (s_tmc_serial.available()) {
        s_tmc_serial.read();
        if (millis() - t0 > 10) break; // guard
    }
}

void tmc2209_write_reg(uint8_t driver_address, uint8_t reg, uint32_t value)
{
    uint8_t pkt[8];
    pkt[0] = 0x05;
    pkt[1] = driver_address;
    pkt[2] = reg | 0x80; // write bit
    pkt[3] = (value >> 24) & 0xFF;
    pkt[4] = (value >> 16) & 0xFF;
    pkt[5] = (value >>  8) & 0xFF;
    pkt[6] = (value      ) & 0xFF;
    pkt[7] = crc8(pkt, 7);

    flush_rx();
    s_tmc_serial.write(pkt, 8);
    s_tmc_serial.flush(); // wait for TX to complete

    // On single-wire: discard the 8-byte echo that comes back on RX
    uint32_t t0 = millis();
    int echo_count = 0;
    while (echo_count < 8 && (millis() - t0) < 20) {
        if (s_tmc_serial.available()) {
            s_tmc_serial.read();
            echo_count++;
        }
    }
}

bool tmc2209_read_reg(uint8_t driver_address, uint8_t reg, uint32_t *out_value)
{
    // Send read request (4 bytes)
    uint8_t req[4];
    req[0] = 0x05;
    req[1] = driver_address;
    req[2] = reg;
    req[3] = crc8(req, 3);

    flush_rx();
    s_tmc_serial.write(req, 4);
    s_tmc_serial.flush();

    // Discard 4-byte echo
    uint32_t t0 = millis();
    int cnt = 0;
    while (cnt < 4 && (millis() - t0) < 10) {
        if (s_tmc_serial.available()) { s_tmc_serial.read(); cnt++; }
    }

    // Read 8-byte reply from slave
    uint8_t reply[8];
    t0 = millis();
    cnt = 0;
    while (cnt < 8 && (millis() - t0) < 20) {
        if (s_tmc_serial.available()) {
            reply[cnt++] = (uint8_t)s_tmc_serial.read();
        }
    }
    if (cnt < 8) {
        Serial.printf("[tmc2209] read timeout (addr=%d reg=0x%02X got=%d)\n",
                      driver_address, reg, cnt);
        return false;
    }

    // Validate CRC
    uint8_t expected_crc = crc8(reply, 7);
    if (reply[7] != expected_crc) {
        Serial.printf("[tmc2209] CRC error (addr=%d reg=0x%02X exp=0x%02X got=0x%02X)\n",
                      driver_address, reg, expected_crc, reply[7]);
        return false;
    }

    *out_value = ((uint32_t)reply[3] << 24)
               | ((uint32_t)reply[4] << 16)
               | ((uint32_t)reply[5] <<  8)
               | ((uint32_t)reply[6]      );
    return true;
}

// ── Driver configuration ──────────────────────────────────────────────────────
void tmc2209_configure(uint8_t driver_address)
{
    // GCONF: enable PDN_UART, mstep_reg_select (use MRES register), i_scale_analog=0
    //   bit 6: pdn_disable  = 1  (PDN not used for power down)
    //   bit 7: mstep_reg_select = 1 (use MSTEP register, not MS1/MS2 pins)
    //   bit 0: i_scale_analog = 0 (use internal reference)
    uint32_t gconf = (1UL << 6) | (1UL << 7);
    tmc2209_write_reg(driver_address, TMC_REG_GCONF, gconf);

    // IHOLD_IRUN:
    //   bits [4:0]   IHOLD  – hold current  (0–31)  → ~40 % of run current
    //   bits [12:8]  IRUN   – run  current  (0–31)  → full scale
    //   bits [19:16] IHOLDDELAY (0–15)
    //
    // Mapping: I_RMS = (IRUN + 1) / 32 * V_FS / R_SENSE * 0.7071
    // With R_SENSE=0.11 Ω, V_FS=0.325 V, 800 mA RMS → IRUN ≈ 19
    const uint8_t IRUN  = 19; // ≈ 800 mA RMS
    const uint8_t IHOLD = 8;  // ≈ 40 %  of IRUN
    const uint8_t IHOLDDELAY = 6;
    uint32_t ihold_irun = ((uint32_t)IHOLDDELAY << 16)
                        | ((uint32_t)IRUN        <<  8)
                        | ((uint32_t)IHOLD       <<  0);
    tmc2209_write_reg(driver_address, TMC_REG_IHOLD_IRUN, ihold_irun);

    // TPOWERDOWN: delay before transitioning to hold current (0–255 × 2^18 cycles)
    tmc2209_write_reg(driver_address, TMC_REG_TPOWERDOWN, 20);

    // CHOPCONF: set microstep resolution
    //   bits [27:24] MRES:  0=256, 1=128, 2=64, 3=32, 4=16, 5=8, 6=4, 7=2, 8=1
    //   bit  [28]    intpol: 1 = interpolate to 256 µsteps
    //   Standard SpreadCycle: TBL=1 (2), TOFF=4, HSTRT=4, HEND=0
    uint8_t mres;
    switch (TMC_MICROSTEP_RES) {
        case 256: mres = 0; break;
        case 128: mres = 1; break;
        case  64: mres = 2; break;
        case  32: mres = 3; break;
        case  16: mres = 4; break;
        case   8: mres = 5; break;
        case   4: mres = 6; break;
        case   2: mres = 7; break;
        default:  mres = 8; break; // full step
    }
    uint32_t chopconf = 0x10000053UL; // TBL=1, TOFF=3 default
    chopconf &= ~(0xFUL << 24);       // clear MRES
    chopconf |=  ((uint32_t)mres << 24);
    chopconf |=  (1UL << 28);         // intpol = 1
    tmc2209_write_reg(driver_address, TMC_REG_CHOPCONF, chopconf);

    // TCOOLTHRS: lower velocity threshold for StallGuard to be active
    tmc2209_write_reg(driver_address, TMC_REG_TCOOLTHRS, TMC_TCOOLTHRS);

    // COOLCONF: StallGuard threshold (SGT bits [14:8])
    uint32_t coolconf = ((uint32_t)(TMC_STALLGUARD_THR & 0x7F) << 8);
    tmc2209_write_reg(driver_address, TMC_REG_COOLCONF, coolconf);

    // PWMCONF: enable StealthChop2 with auto-tuning (reset-default is usually fine)
    // Keep defaults – just force stealthchop threshold high so it runs stealthchop
    // at low speeds and switches to spreadcycle above TPWMTHRS.
    tmc2209_write_reg(driver_address, TMC_REG_TPWMTHRS, 500);

    Serial.printf("[tmc2209] driver %d configured (IRUN=%d IHOLD=%d MRES=%d)\n",
                  driver_address, IRUN, IHOLD, TMC_MICROSTEP_RES);
}

// ── Public init ───────────────────────────────────────────────────────────────
void tmc2209_init(int tx_pin, int rx_pin)
{
    s_tmc_serial.begin(TMC_UART_BAUD, SERIAL_8N1, rx_pin, tx_pin);
    delay(50); // allow drivers to power up

    Serial.println("[tmc2209] initialising UART bus");

    tmc2209_configure(TMC_ADDR_RAIL);
    tmc2209_configure(TMC_ADDR_Z);

    Serial.println("[tmc2209] all drivers configured");
}

// ── StallGuard read ───────────────────────────────────────────────────────────
uint16_t tmc2209_get_stallguard(uint8_t driver_address)
{
    uint32_t val = 0;
    if (!tmc2209_read_reg(driver_address, TMC_REG_DRV_STATUS, &val)) {
        return 0xFFFF; // error sentinel
    }
    // SG_RESULT is bits [9:0] of DRV_STATUS
    return (uint16_t)(val & 0x3FF);
}
