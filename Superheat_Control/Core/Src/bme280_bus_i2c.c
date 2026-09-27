#include "bme280.h"
#include "i2c1_bus.h"

/* BME280 on the shared I2C1 bus (PB8 SCL / PB9 SDA), alongside the LCD.
 * Wire the sensor's CSB pin straight to 3V3: the BME280 latches into SPI mode
 * for good if CSB is ever pulled low after power-up. */

/* 7-bit address: 0x76 with the BME280's SDO pin tied to GND, 0x77 with SDO
 * tied to VDDIO. Override with -DBME280_I2C_ADDR=0x77 if needed. */
#ifndef BME280_I2C_ADDR
#define BME280_I2C_ADDR 0x76
#endif

static int i2c_init(void)
{
  return I2C1_Init();
}

static int i2c_read(uint8_t reg, uint8_t *buf, uint16_t len)
{
  return I2C1_MemRead(BME280_I2C_ADDR, reg, buf, len);
}

static int i2c_write(uint8_t reg, uint8_t value)
{
  return I2C1_MemWrite(BME280_I2C_ADDR, reg, &value, 1);
}

const BME280_Bus_t bme280_bus = {
  .name  = "I2C",
  .init  = i2c_init,
  .read  = i2c_read,
  .write = i2c_write,
};
