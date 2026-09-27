#ifndef LCD1602_H
#define LCD1602_H

#include <stdint.h>

/* 16x2 HD44780 character LCD behind a PCF8574 I2C backpack, on the shared
 * I2C1 bus. The HD44780 runs in 4-bit mode: the PCF8574's 8 output pins
 * carry one data nibble plus the RS/RW/EN/backlight control lines. */

#define LCD1602_COLS 16
#define LCD1602_ROWS 2

/* 7-bit address: 0x27 for the common PCF8574T backpack, 0x3F for PCF8574AT.
 * Override with -DLCD1602_I2C_ADDR=0x3F if needed. */
#ifndef LCD1602_I2C_ADDR
#define LCD1602_I2C_ADDR 0x27
#endif

/* delay_ms is passed in so the driver doesn't depend on the RTOS - the
 * caller supplies osDelay from a task, or HAL_Delay before the scheduler. */
int LCD1602_Init(void (*delay_ms)(uint32_t ms));
int LCD1602_Clear(void);

/* Writes text at the start of a row, padding with spaces to the full width
 * so a shorter string overwrites whatever was there before. */
int LCD1602_WriteLine(uint8_t row, const char *text);

#endif /* LCD1602_H */
