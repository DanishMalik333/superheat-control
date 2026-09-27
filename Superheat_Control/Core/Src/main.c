/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "cmsis_os.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "pid.h"
#include "bme280.h"
#include "i2c1_bus.h"
#include "lcd1602.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define PID_KP        0.1
#define PID_KI        0.015
#define PID_TS        1.0
#define PID_OUT_MIN   0.1
#define PID_OUT_MAX   0.9

#define LINK_RX_BUF_LEN   32
#define SETPOINT_DEGC     10.0 /* superheat setpoint, degC */
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
SPI_HandleTypeDef hspi1;

UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;

/* Definitions for LinkTask */
osThreadId_t LinkTaskHandle;
const osThreadAttr_t LinkTask_attributes = {
  .name = "LinkTask",
  .stack_size = 512 * 4,
  .priority = (osPriority_t) osPriorityAboveNormal,
};
/* Definitions for SensorTask */
osThreadId_t SensorTaskHandle;
const osThreadAttr_t SensorTask_attributes = {
  .name = "SensorTask",
  .stack_size = 256 * 4,
  .priority = (osPriority_t) osPriorityNormal,
};
/* Definitions for ControlTask */
osThreadId_t ControlTaskHandle;
const osThreadAttr_t ControlTask_attributes = {
  .name = "ControlTask",
  .stack_size = 512 * 4,
  .priority = (osPriority_t) osPriorityNormal,
};
/* Definitions for SimTempQueue */
osMessageQueueId_t SimTempQueueHandle;
const osMessageQueueAttr_t SimTempQueue_attributes = {
  .name = "SimTempQueue"
};
/* Definitions for ValveOutputQueue */
osMessageQueueId_t ValveOutputQueueHandle;
const osMessageQueueAttr_t ValveOutputQueue_attributes = {
  .name = "ValveOutputQueue"
};
/* USER CODE BEGIN PV */
static PID_t pid;

/* Interrupt-driven USART1 line reception. HAL_UART_Receive_IT is re-armed for
 * one byte at a time from the RxCpltCallback, so incoming bytes are captured
 * by the peripheral/ISR regardless of what the main loop is doing, avoiding
 * the overrun that polling HAL_UART_Receive suffered from. */
static uint8_t link_rx_byte;
static char link_rx_line[LINK_RX_BUF_LEN];
static volatile uint16_t link_rx_len = 0;
static volatile uint8_t link_rx_line_ready = 0;

/* Latest BME280 ambient reading, written by SensorTask and read by LinkTask
 * (sent to Board 2 as the plant's load disturbance) and ControlTask (logged).
 * Kept as a float rather than a double on purpose: an aligned 32-bit load or
 * store is a single atomic access on the Cortex-M4, so readers can never see
 * a half-written value and no mutex is needed. NAN means "no valid reading"
 * (sensor missing or bus error), in which case Board 2 is sent no ambient. */
static volatile float latest_bme280_degC = NAN;
static int bme280_ok = 0;

/* Latest loop values for the LCD, written by ControlTask and read by
 * DisplayTask. Floats for the same single-access atomicity reason as above. */
static volatile float display_superheat_degC = NAN;
static volatile float display_valve = NAN;

/* DisplayTask is created in the RTOS_THREADS user section rather than through
 * CubeMX, so its definition lives here instead of in the generated block. */
osThreadId_t DisplayTaskHandle;
const osThreadAttr_t DisplayTask_attributes = {
  .name = "DisplayTask",
  .stack_size = 512 * 4, /* snprintf float formatting is stack-heavy */
  .priority = (osPriority_t) osPriorityBelowNormal,
};
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_SPI1_Init(void);
static void MX_USART1_UART_Init(void);
void StartLinkTask(void *argument);
void StartSensorTask(void *argument);
void StartControlTask(void *argument);

/* USER CODE BEGIN PFP */
static void StartDisplayTask(void *argument);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
void vApplicationStackOverflowHook(TaskHandle_t xTask, char *pcTaskName)
{
  (void)xTask;
  printf("!!! STACK OVERFLOW in task: %s\r\n", pcTaskName);
  __disable_irq();
  for (;;) { }
}

void vApplicationMallocFailedHook(void)
{
  printf("!!! FreeRTOS heap allocation failed (out of heap)\r\n");
  __disable_irq();
  for (;;) { }
}

int __io_putchar(int ch)
{
  HAL_UART_Transmit(&huart2, (uint8_t *)&ch, 1, HAL_MAX_DELAY);
  return ch;
}

/* Called from USART1_IRQHandler via HAL_UART_IRQHandler whenever one byte has
 * been received. Assembles line_rx_line and re-arms the next single-byte
 * receive so bytes are never missed while the main loop is busy elsewhere. */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
  if (huart->Instance != USART1)
  {
    return;
  }

  uint8_t ch = link_rx_byte;

  if (!link_rx_line_ready)
  {
    if (ch == '\n')
    {
      link_rx_line[link_rx_len] = '\0';
      link_rx_line_ready = 1;
    }
    else if (ch != '\r')
    {
      if (link_rx_len < LINK_RX_BUF_LEN - 1)
      {
        link_rx_line[link_rx_len++] = (char)ch;
      }
      else
      {
        /* Line too long: drop it and resync on the next '\n'. */
        link_rx_len = 0;
      }
    }
  }

  HAL_UART_Receive_IT(&huart1, &link_rx_byte, 1);
}

/* Waits (with a timeout) for HAL_UART_RxCpltCallback to assemble one
 * "<tick>,<value>\r\n" line from USART1. Returns 1 on success. */
static int Link_ReceiveLine(unsigned long *tick, double *value)
{
  uint32_t start = HAL_GetTick();

  while (!link_rx_line_ready)
  {
    if ((HAL_GetTick() - start) > 500)
    {
      return 0;
    }

    osDelay(1);
  }

  int ok = (link_rx_len > 0) && (sscanf(link_rx_line, "%lu,%lf", tick, value) == 2);

  link_rx_len = 0;
  link_rx_line_ready = 0;

  return ok;
}

/* Sends "<tick>,<valve>,<ambient>\r\n" to Board 2, or "<tick>,<valve>\r\n"
 * when there is no valid ambient reading - Board 2 then holds the last
 * disturbance it received. */
static void Link_SendLine(unsigned long tick, double value, float ambient_degC)
{
  char out[LINK_RX_BUF_LEN];
  int n;

  if (isnan(ambient_degC))
  {
    n = snprintf(out, sizeof(out), "%lu,%.4f\r\n", tick, value);
  }
  else
  {
    n = snprintf(out, sizeof(out), "%lu,%.4f,%.2f\r\n", tick, value, (double)ambient_degC);
  }

  if (n < 0 || n >= (int)sizeof(out))
  {
    return; /* would have been truncated - never send a partial frame */
  }

  HAL_UART_Transmit(&huart1, (uint8_t *)out, (uint16_t)n, 100);
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_USART2_UART_Init();
  MX_SPI1_Init();
  MX_USART1_UART_Init();
  /* USER CODE BEGIN 2 */
  HAL_UART_Receive_IT(&huart1, &link_rx_byte, 1);

  uint8_t chip_id = 0;
  bme280_ok = (BME280_Init(&bme280_bus, &chip_id) == 0);
  if (bme280_ok)
  {
    printf("# BME280 over %s, chip_id=0x%02X\r\n", bme280_bus.name, chip_id);
  }
  else
  {
    printf("# BME280 over %s not found (chip_id=0x%02X, expect 0x%02X) - running without ambient disturbance\r\n",
           bme280_bus.name, chip_id, BME280_CHIP_ID_VALUE);
  }

  PID_Init(&pid, PID_KP, PID_KI, PID_TS, PID_OUT_MIN, PID_OUT_MAX);

  printf("tick,bme280_degC,plant_degC,valve,setpoint_degC\r\n");
  /* USER CODE END 2 */

  /* Init scheduler */
  osKernelInitialize();

  /* USER CODE BEGIN RTOS_MUTEX */
  /* SensorTask (I2C build) and DisplayTask share I2C1 */
  I2C1_CreateMutex();
  /* USER CODE END RTOS_MUTEX */

  /* USER CODE BEGIN RTOS_SEMAPHORES */
  /* add semaphores, ... */
  /* USER CODE END RTOS_SEMAPHORES */

  /* USER CODE BEGIN RTOS_TIMERS */
  /* start timers, add new ones, ... */
  /* USER CODE END RTOS_TIMERS */

  /* Create the queue(s) */
  /* creation of SimTempQueue */
  SimTempQueueHandle = osMessageQueueNew (1, sizeof(double), &SimTempQueue_attributes);

  /* creation of ValveOutputQueue */
  ValveOutputQueueHandle = osMessageQueueNew (1, sizeof(double), &ValveOutputQueue_attributes);

  /* USER CODE BEGIN RTOS_QUEUES */
  /* add queues, ... */
  /* USER CODE END RTOS_QUEUES */

  /* Create the thread(s) */
  /* creation of LinkTask */
  LinkTaskHandle = osThreadNew(StartLinkTask, NULL, &LinkTask_attributes);

  /* creation of SensorTask */
  SensorTaskHandle = osThreadNew(StartSensorTask, NULL, &SensorTask_attributes);

  /* creation of ControlTask */
  ControlTaskHandle = osThreadNew(StartControlTask, NULL, &ControlTask_attributes);

  /* USER CODE BEGIN RTOS_THREADS */
  DisplayTaskHandle = osThreadNew(StartDisplayTask, NULL, &DisplayTask_attributes);
  /* USER CODE END RTOS_THREADS */

  /* USER CODE BEGIN RTOS_EVENTS */
  /* add events, ... */
  /* USER CODE END RTOS_EVENTS */

  /* Start scheduler */
  osKernelStart();

  /* We should never get here as control is now taken by the scheduler */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE2);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 16;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
  RCC_OscInitStruct.PLL.PLLQ = 7;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief SPI1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_SPI1_Init(void)
{

  /* USER CODE BEGIN SPI1_Init 0 */

  /* USER CODE END SPI1_Init 0 */

  /* USER CODE BEGIN SPI1_Init 1 */

  /* USER CODE END SPI1_Init 1 */
  /* SPI1 parameter configuration*/
  hspi1.Instance = SPI1;
  hspi1.Init.Mode = SPI_MODE_MASTER;
  hspi1.Init.Direction = SPI_DIRECTION_2LINES;
  hspi1.Init.DataSize = SPI_DATASIZE_8BIT;
  hspi1.Init.CLKPolarity = SPI_POLARITY_LOW;
  hspi1.Init.CLKPhase = SPI_PHASE_1EDGE;
  hspi1.Init.NSS = SPI_NSS_SOFT;
  hspi1.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_16;
  hspi1.Init.FirstBit = SPI_FIRSTBIT_MSB;
  hspi1.Init.TIMode = SPI_TIMODE_DISABLE;
  hspi1.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  hspi1.Init.CRCPolynomial = 10;
  if (HAL_SPI_Init(&hspi1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN SPI1_Init 2 */

  /* USER CODE END SPI1_Init 2 */

}

/**
  * @brief USART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART1_UART_Init(void)
{

  /* USER CODE BEGIN USART1_Init 0 */

  /* USER CODE END USART1_Init 0 */

  /* USER CODE BEGIN USART1_Init 1 */

  /* USER CODE END USART1_Init 1 */
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART1_Init 2 */

  /* USER CODE END USART1_Init 2 */

}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(BME280_CS_GPIO_Port, BME280_CS_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin : B1_Pin */
  GPIO_InitStruct.Pin = B1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(B1_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pin : BME280_CS_Pin */
  GPIO_InitStruct.Pin = BME280_CS_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(BME280_CS_GPIO_Port, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
static void rtos_delay_ms(uint32_t ms)
{
  osDelay(ms); /* configTICK_RATE_HZ is 1000, so ticks == ms */
}

/* Shows the live loop state on the 16x2 LCD:
 *   SH:10.2 SP:10.0      superheat and setpoint, degC
 *   V: 50%  Amb:23.4     valve opening and BME280 ambient, degC
 * Lowest-priority task, since the display is for the operator only and must
 * never delay the control or link tasks. */
static void StartDisplayTask(void *argument)
{
  (void)argument;
  char line[LCD1602_COLS + 1];

  if (LCD1602_Init(rtos_delay_ms) != 0)
  {
    printf("# LCD not found at I2C address 0x%02X - display disabled\r\n", LCD1602_I2C_ADDR);
    osThreadExit();
  }

  for (;;)
  {
    float superheat = display_superheat_degC;
    float valve = display_valve;
    float ambient = latest_bme280_degC;

    if (isnan(superheat))
    {
      snprintf(line, sizeof(line), "SH:--.- SP:%.1f", SETPOINT_DEGC);
    }
    else
    {
      snprintf(line, sizeof(line), "SH:%.1f SP:%.1f", (double)superheat, SETPOINT_DEGC);
    }
    LCD1602_WriteLine(0, line);

    if (isnan(ambient))
    {
      snprintf(line, sizeof(line), "V:%3.0f%%  Amb:--.-", isnan(valve) ? 0.0 : (double)valve * 100.0);
    }
    else
    {
      snprintf(line, sizeof(line), "V:%3.0f%%  Amb:%.1f", isnan(valve) ? 0.0 : (double)valve * 100.0,
               (double)ambient);
    }
    LCD1602_WriteLine(1, line);

    osDelay(500);
  }
}
/* USER CODE END 4 */

/* USER CODE BEGIN Header_StartLinkTask */
/**
  * @brief  Function implementing the LinkTask thread.
  * @param  argument: Not used
  * @retval None
  */
/* USER CODE END Header_StartLinkTask */
void StartLinkTask(void *argument)
{
  /* USER CODE BEGIN 5 */
  unsigned long tick = 0;
  double valve_output = PID_OUT_MIN;

  for(;;)
  {
    /* Pick up the latest valve output computed by ControlTask, if any new
     * one is available; otherwise keep sending the last known value. */
    osMessageQueueGet(ValveOutputQueueHandle, &valve_output, NULL, 0);

    unsigned long echoed_tick = 0;
    double received_temp = 0.0;

    Link_SendLine(tick, valve_output, latest_bme280_degC);

    if (Link_ReceiveLine(&echoed_tick, &received_temp))
    {
      osMessageQueueReset(SimTempQueueHandle);
      osMessageQueuePut(SimTempQueueHandle, &received_temp, 0, 0);
    }
    else
    {
      printf("# HIL link: malformed/missing frame, holding last simulated_temp\r\n");
    }

    tick++;
    osDelay(1000);
  }
  /* USER CODE END 5 */
}

/* USER CODE BEGIN Header_StartSensorTask */
/**
* @brief Function implementing the SensorTask thread.
* @param argument: Not used
* @retval None
*/
/* USER CODE END Header_StartSensorTask */
void StartSensorTask(void *argument)
{
  /* USER CODE BEGIN StartSensorTask */
  for(;;)
  {
    if (!bme280_ok)
    {
      osDelay(1000); /* no sensor found at startup - nothing to sample */
      continue;
    }

    /* Forced mode powers down after one measurement; re-trigger each cycle */
    double temp_degC = 0.0;
    int ok = (BME280_TriggerMeasurement() == 0);
    osDelay(BME280_MEAS_TIME_MS); /* allow conversion to complete */

    if (ok && BME280_ReadTemperature(&temp_degC) == 0)
    {
      latest_bme280_degC = (float)temp_degC;
    }
    else
    {
      /* A bus error invalidates the reading rather than freezing the last
       * value, so Board 2 stops being fed a stale disturbance. */
      latest_bme280_degC = NAN;
    }

    osDelay(1000 - BME280_MEAS_TIME_MS); /* sample once per second overall */
  }
  /* USER CODE END StartSensorTask */
}

/* USER CODE BEGIN Header_StartControlTask */
/**
* @brief Function implementing the ControlTask thread.
* @param argument: Not used
* @retval None
*/
/* USER CODE END Header_StartControlTask */
void StartControlTask(void *argument)
{
  /* USER CODE BEGIN StartControlTask */
  unsigned long tick = 0;
  double simulated_temp = 0.0;

  for(;;)
  {
    /* Use the latest simulated temp from LinkTask if a new one arrived
     * since last cycle; otherwise hold the previous value. */
    osMessageQueueGet(SimTempQueueHandle, &simulated_temp, NULL, 0);

    double valve_output = PID_Update(&pid, SETPOINT_DEGC, simulated_temp);

    osMessageQueueReset(ValveOutputQueueHandle);
    osMessageQueuePut(ValveOutputQueueHandle, &valve_output, 0, 0);

    display_superheat_degC = (float)simulated_temp;
    display_valve = (float)valve_output;

    printf("%lu,%.2f,%.4f,%.3f,%.2f\r\n",
           tick, (double)latest_bme280_degC, simulated_temp, valve_output, SETPOINT_DEGC);

    tick++;
    osDelay(1000);
  }
  /* USER CODE END StartControlTask */
}

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
