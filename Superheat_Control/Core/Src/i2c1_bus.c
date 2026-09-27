#include "i2c1_bus.h"
#include "main.h"
#include "cmsis_os.h"

/* I2C1 is configured here rather than in CubeMX, so if it's ever enabled in
 * the .ioc, remove HAL_I2C_MspInit below since CubeMX will generate its own
 * in stm32f4xx_hal_msp.c. */

#define I2C1_TIMEOUT_MS 100

static I2C_HandleTypeDef hi2c1;
static osMutexId_t i2c1_mutex = NULL;

static const osMutexAttr_t i2c1_mutex_attr = {
  .name = "I2C1Mutex",
  .attr_bits = osMutexPrioInherit, /* avoid priority inversion between LCD and sensor tasks */
};

void HAL_I2C_MspInit(I2C_HandleTypeDef *hi2c)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  if (hi2c->Instance != I2C1)
  {
    return;
  }

  __HAL_RCC_GPIOB_CLK_ENABLE();

  /* Open-drain as I2C requires. Internal pull-ups are weak (~40 kOhm) and
   * only a fallback - the BME280 and LCD backpack boards fit external ones. */
  GPIO_InitStruct.Pin = GPIO_PIN_8 | GPIO_PIN_9;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_OD;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF4_I2C1;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  __HAL_RCC_I2C1_CLK_ENABLE();
}

int I2C1_Init(void)
{
  if (hi2c1.Instance == I2C1)
  {
    return 0; /* already initialised by the other device on the bus */
  }

  hi2c1.Instance = I2C1;
  hi2c1.Init.ClockSpeed = 100000;
  hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;
  hi2c1.Init.OwnAddress1 = 0;
  hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c1.Init.OwnAddress2 = 0;
  hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;

  if (HAL_I2C_Init(&hi2c1) != HAL_OK)
  {
    hi2c1.Instance = NULL;
    return -1;
  }

  return 0;
}

void I2C1_CreateMutex(void)
{
  if (i2c1_mutex == NULL)
  {
    i2c1_mutex = osMutexNew(&i2c1_mutex_attr);
  }
}

static void bus_lock(void)
{
  if (i2c1_mutex != NULL)
  {
    osMutexAcquire(i2c1_mutex, osWaitForever);
  }
}

static void bus_unlock(void)
{
  if (i2c1_mutex != NULL)
  {
    osMutexRelease(i2c1_mutex);
  }
}

/* The HAL expects the 7-bit address shifted left by one. Mem* calls do the
 * register-pointer write and the repeated-start read in one transaction. */
int I2C1_MemRead(uint8_t addr7, uint8_t reg, uint8_t *buf, uint16_t len)
{
  bus_lock();
  HAL_StatusTypeDef status = HAL_I2C_Mem_Read(&hi2c1, (uint16_t)(addr7 << 1), reg,
                                              I2C_MEMADD_SIZE_8BIT, buf, len, I2C1_TIMEOUT_MS);
  bus_unlock();
  return (status == HAL_OK) ? 0 : -1;
}

int I2C1_MemWrite(uint8_t addr7, uint8_t reg, const uint8_t *buf, uint16_t len)
{
  bus_lock();
  HAL_StatusTypeDef status = HAL_I2C_Mem_Write(&hi2c1, (uint16_t)(addr7 << 1), reg,
                                               I2C_MEMADD_SIZE_8BIT, (uint8_t *)buf, len,
                                               I2C1_TIMEOUT_MS);
  bus_unlock();
  return (status == HAL_OK) ? 0 : -1;
}

int I2C1_Transmit(uint8_t addr7, const uint8_t *buf, uint16_t len)
{
  bus_lock();
  HAL_StatusTypeDef status = HAL_I2C_Master_Transmit(&hi2c1, (uint16_t)(addr7 << 1),
                                                     (uint8_t *)buf, len, I2C1_TIMEOUT_MS);
  bus_unlock();
  return (status == HAL_OK) ? 0 : -1;
}
