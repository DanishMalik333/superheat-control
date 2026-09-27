#include "bme280.h"

#define BME280_REG_CHIP_ID        0xD0
#define BME280_REG_CALIB_T_START  0x88 /* dig_T1..dig_T3, 6 bytes */
#define BME280_REG_CTRL_MEAS      0xF4
#define BME280_REG_TEMP_MSB       0xFA /* temp_msb, temp_lsb, temp_xlsb, 3 bytes */

/* ctrl_meas: osrs_t=001 (x1), osrs_p=000 (skipped), mode=01 (forced) */
#define BME280_CTRL_MEAS_FORCED_T 0x25

static const BME280_Bus_t *bme_bus;
static uint16_t dig_T1;
static int16_t  dig_T2;
static int16_t  dig_T3;

/* Checks the chip ID and reads the temperature calibration constants.
 * Returns 0 on success; chip_id is filled in either way for diagnostics. */
int BME280_Init(const BME280_Bus_t *bus, uint8_t *chip_id)
{
  uint8_t buf[6];

  bme_bus = bus;
  *chip_id = 0;

  if (bme_bus->init() != 0)
  {
    return -1;
  }
  if (bme_bus->read(BME280_REG_CHIP_ID, chip_id, 1) != 0 || *chip_id != BME280_CHIP_ID_VALUE)
  {
    return -1;
  }
  if (bme_bus->read(BME280_REG_CALIB_T_START, buf, 6) != 0)
  {
    return -1;
  }

  dig_T1 = (uint16_t)((buf[1] << 8) | buf[0]);
  dig_T2 = (int16_t)((buf[3] << 8) | buf[2]);
  dig_T3 = (int16_t)((buf[5] << 8) | buf[4]);

  return 0;
}

/* Forced mode powers down after one measurement, so this must be called
 * before every read. Wait BME280_MEAS_TIME_MS before BME280_ReadTemperature. */
int BME280_TriggerMeasurement(void)
{
  return bme_bus->write(BME280_REG_CTRL_MEAS, BME280_CTRL_MEAS_FORCED_T);
}

/* Reads the raw 20-bit temperature and applies the datasheet's double
 * precision compensation formula. Output value of 51.23 equals 51.23 DegC. */
int BME280_ReadTemperature(double *temp_degC)
{
  uint8_t buf[3];
  double var1, var2;

  if (bme_bus->read(BME280_REG_TEMP_MSB, buf, 3) != 0)
  {
    return -1;
  }

  /* temp_msb:temp_lsb:temp_xlsb[7:4] packed into a 20-bit raw value */
  int32_t adc_T = (int32_t)(((uint32_t)buf[0] << 12) | ((uint32_t)buf[1] << 4) | (buf[2] >> 4));

  var1 = (((double)adc_T) / 16384.0 - ((double)dig_T1) / 1024.0) * ((double)dig_T2);
  var2 = ((((double)adc_T) / 131072.0 - ((double)dig_T1) / 8192.0) *
          (((double)adc_T) / 131072.0 - ((double)dig_T1) / 8192.0)) * ((double)dig_T3);
  *temp_degC = (var1 + var2) / 5120.0;

  return 0;
}
