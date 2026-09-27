#ifndef LCD2004_H
#define LCD2004_H

#include <stdint.h>

/* 20x4 HD44780 character LCD behind a PCF8574 I2C backpack, on the shared
 * I2C1 bus. The HD44780 runs in 4-bit mode: the PCF8574's 8 output pins
 * carry one data nibble plus the RS/RW/EN/backlight control lines. */

#define LCD2004_COLS 20
#define LCD2004_ROWS 4

/* 7-bit address: 0x27 for the common PCF8574T backpack, 0x3F for PCF8574AT.
 * Override with -DLCD2004_I2C_ADDR=0x3F if needed. */
#ifndef LCD2004_I2C_ADDR
#define LCD2004_I2C_ADDR 0x27
#endif

/* delay_ms is passed in so the driver doesn't depend on the RTOS - the
 * caller supplies osDelay from a task, or HAL_Delay before the scheduler. */
int LCD2004_Init(void (*delay_ms)(uint32_t ms));
int LCD2004_Clear(void);

/* Writes text at the start of a row, padding with spaces to the full width
 * so a shorter string overwrites whatever was there before. */
int LCD2004_WriteLine(uint8_t row, const char *text);

#endif /* LCD2004_H */
