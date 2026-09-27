#ifndef BME280_H
#define BME280_H

#include <stdint.h>

/* Bus abstraction: the driver only needs register-level access, so SPI and
 * I2C each implement these functions and the driver above them is identical
 * for both. All functions return 0 on success, non-zero on a bus error. */
typedef struct
{
  const char *name;
  int (*init)(void);
  int (*read)(uint8_t reg, uint8_t *buf, uint16_t len);
  int (*write)(uint8_t reg, uint8_t value);
} BME280_Bus_t;

/* Provided by bme280_bus_spi.c or bme280_bus_i2c.c - only one is compiled,
 * selected by the BME280_BUS CMake option. */
extern const BME280_Bus_t bme280_bus;

#define BME280_CHIP_ID_VALUE    0x60

/* Time from triggering a forced-mode measurement until the result is ready
 * (temperature only, x1 oversampling: ~2.3 ms typical per datasheet). */
#define BME280_MEAS_TIME_MS     10

int BME280_Init(const BME280_Bus_t *bus, uint8_t *chip_id);
int BME280_TriggerMeasurement(void);
int BME280_ReadTemperature(double *temp_degC);

#endif /* BME280_H */
