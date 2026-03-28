#pragma once
/*
 * tmc2209.h  –  TMC2209 UART single-wire configuration
 *
 * The TMC2209 UART interface uses a single half-duplex wire.
 * We use one HardwareSerial port (Serial2) at 115200 baud.
 *
 * Driver addressing:
 *   MS1/MS2 pulled low/high select addresses 0–3.
 *   Rail axis driver  → address 0 (both MS1&MS2 to GND via solder bridge)
 *   Z    axis driver  → address 1 (MS1 to VCC, MS2 to GND)
 *
 * Protocol reference: Trinamic TMC2209 datasheet §5 (UART)
 */

#ifndef TMC2209_H
#define TMC2209_H

#include <stdint.h>
#include <stdbool.h>

// ── Hardware ─────────────────────────────────────────────────────────────────
#define TMC_UART_TX_PIN     17    // ESP32 GPIO17 → TX2
#define TMC_UART_RX_PIN     16    // ESP32 GPIO16 → RX2 (also receives TX echo)
#define TMC_UART_BAUD       115200

#define TMC_ADDR_RAIL       0
#define TMC_ADDR_Z          1

// ── Motion / current settings ────────────────────────────────────────────────
#define TMC_MICROSTEP_RES   16    // 16 microsteps
#define TMC_RMS_CURRENT_MA  800   // RMS motor current in mA
#define TMC_STALLGUARD_THR  10    // StallGuard4 threshold (0–255)
#define TMC_TCOOLTHRS       300   // Lower velocity threshold for StallGuard

// ── Register addresses (subset) ──────────────────────────────────────────────
#define TMC_REG_GCONF        0x00
#define TMC_REG_GSTAT        0x01
#define TMC_REG_IFCNT        0x02
#define TMC_REG_SLAVECONF    0x03
#define TMC_REG_IOIN         0x06
#define TMC_REG_IHOLD_IRUN   0x10
#define TMC_REG_TPOWERDOWN   0x11
#define TMC_REG_TSTEP        0x12
#define TMC_REG_TPWMTHRS     0x13
#define TMC_REG_TCOOLTHRS    0x14
#define TMC_REG_MSCNT        0x6A
#define TMC_REG_CHOPCONF     0x6C
#define TMC_REG_COOLCONF     0x6D
#define TMC_REG_DRV_STATUS   0x6F
#define TMC_REG_PWMCONF      0x70
#define TMC_REG_SG_RESULT    0x41   // StallGuard result (read)

// ── Public API ───────────────────────────────────────────────────────────────

/**
 * Initialise the UART bus and configure both TMC2209 drivers.
 * @param tx_pin  ESP32 TX GPIO (connected to single-wire UART on both drivers)
 * @param rx_pin  ESP32 RX GPIO (for echo / read-back)
 */
void tmc2209_init(int tx_pin, int rx_pin);

/**
 * Configure one driver:
 *   - Microstep resolution
 *   - Run/hold current
 *   - StallGuard threshold
 *   - SpreadCycle vs StealthChop threshold
 *
 * @param driver_address  0–3 matching hardware MS1/MS2 strapping.
 */
void tmc2209_configure(uint8_t driver_address);

/**
 * Read the StallGuard4 result register for a driver.
 * Lower values indicate more load / stall risk.
 *
 * @param driver_address  0–3
 * @return SG_RESULT value (0–1023), or 0xFFFF on read error.
 */
uint16_t tmc2209_get_stallguard(uint8_t driver_address);

/**
 * Write a 32-bit value to a TMC2209 register over UART.
 */
void tmc2209_write_reg(uint8_t driver_address, uint8_t reg, uint32_t value);

/**
 * Read a 32-bit value from a TMC2209 register over UART.
 * Returns false on CRC / timeout error.
 */
bool tmc2209_read_reg(uint8_t driver_address, uint8_t reg, uint32_t *out_value);

#endif // TMC2209_H
