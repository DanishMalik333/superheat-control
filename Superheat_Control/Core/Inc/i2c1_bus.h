#ifndef I2C1_BUS_H
#define I2C1_BUS_H

#include <stdint.h>

/* Shared I2C1 bus (PB8 SCL / PB9 SDA, 100 kHz) used by the LCD and, in the
 * I2C build, the BME280. The two devices are driven from different FreeRTOS
 * tasks, and the HAL's I2C handle isn't safe to use from two tasks at once,
 * so every transfer below holds a mutex for the duration of the transaction.
 * All functions return 0 on success, non-zero on a bus error. */

int I2C1_Init(void);

/* Call once after osKernelInitialize(). Transfers made before this (device
 * init in main, while only one thread of execution exists) run unlocked. */
void I2C1_CreateMutex(void);

int I2C1_MemRead(uint8_t addr7, uint8_t reg, uint8_t *buf, uint16_t len);
int I2C1_MemWrite(uint8_t addr7, uint8_t reg, const uint8_t *buf, uint16_t len);
int I2C1_Transmit(uint8_t addr7, const uint8_t *buf, uint16_t len);

#endif /* I2C1_BUS_H */
