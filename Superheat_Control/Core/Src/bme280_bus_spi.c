#include "bme280.h"
#include "main.h"

/* SPI1 (PA5 SCK, PA6 MISO, PA7 MOSI) with a software chip select on PB6.
 * The peripheral itself is configured by the CubeMX-generated MX_SPI1_Init. */
extern SPI_HandleTypeDef hspi1;

#define BME280_SPI_READ_BIT   0x80
#define BME280_SPI_TIMEOUT_MS 100

static int spi_init(void)
{
  return 0;
}

static int spi_read(uint8_t reg, uint8_t *buf, uint16_t len)
{
  uint8_t tx = reg | BME280_SPI_READ_BIT;
  HAL_StatusTypeDef status;

  HAL_GPIO_WritePin(BME280_CS_GPIO_Port, BME280_CS_Pin, GPIO_PIN_RESET);
  status = HAL_SPI_Transmit(&hspi1, &tx, 1, BME280_SPI_TIMEOUT_MS);
  if (status == HAL_OK)
  {
    status = HAL_SPI_Receive(&hspi1, buf, len, BME280_SPI_TIMEOUT_MS);
  }
  HAL_GPIO_WritePin(BME280_CS_GPIO_Port, BME280_CS_Pin, GPIO_PIN_SET);

  return (status == HAL_OK) ? 0 : -1;
}

static int spi_write(uint8_t reg, uint8_t value)
{
  uint8_t tx[2];
  HAL_StatusTypeDef status;

  tx[0] = reg & ~BME280_SPI_READ_BIT; /* MSB cleared = write */
  tx[1] = value;

  HAL_GPIO_WritePin(BME280_CS_GPIO_Port, BME280_CS_Pin, GPIO_PIN_RESET);
  status = HAL_SPI_Transmit(&hspi1, tx, 2, BME280_SPI_TIMEOUT_MS);
  HAL_GPIO_WritePin(BME280_CS_GPIO_Port, BME280_CS_Pin, GPIO_PIN_SET);

  return (status == HAL_OK) ? 0 : -1;
}

const BME280_Bus_t bme280_bus = {
  .name  = "SPI",
  .init  = spi_init,
  .read  = spi_read,
  .write = spi_write,
};
