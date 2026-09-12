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
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
#define INPUT_SAMPLE_MS          10U
#define STARTUP_LOCK_MS          2000U
#define HIGH_CONFIRM_SAMPLES    6U   /* 约60 ms高电平才认定有效 */
#define LOW_REARM_SAMPLES       12U  /* 约120 ms低电平后才重新使能 */
#define COMMAND_LOCKOUT_MS      400U

typedef struct
{
  uint8_t high_samples;
  uint8_t low_samples;
  uint8_t armed;
} PulseInputFilter;

static PulseInputFilter stop_filter = {0U, 0U, 0U};
static PulseInputFilter start_filter = {0U, 0U, 0U};
static uint32_t last_sample_tick = 0U;
static uint32_t startup_tick = 0U;
static uint32_t command_lockout_tick = 0U;
static uint16_t startup_low_samples = 0U;
static uint8_t startup_ready = 0U;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */
static uint8_t PulseInput_Update(PulseInputFilter *filter,
                                 GPIO_PinState raw_level);
static void ConveyorInputs_Process(void);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

static uint8_t PulseInput_Update(PulseInputFilter *filter,
                                 GPIO_PinState raw_level)
{
  if (raw_level == GPIO_PIN_SET)
  {
    filter->low_samples = 0U;

    if (filter->armed == 0U)
    {
      return 0U;
    }

    if (filter->high_samples < HIGH_CONFIRM_SAMPLES)
    {
      filter->high_samples++;
    }

    if (filter->high_samples >= HIGH_CONFIRM_SAMPLES)
    {
      filter->high_samples = 0U;
      filter->armed = 0U;
      return 1U;
    }
  }
  else
  {
    filter->high_samples = 0U;

    if (filter->low_samples < LOW_REARM_SAMPLES)
    {
      filter->low_samples++;
    }

    if (filter->low_samples >= LOW_REARM_SAMPLES)
    {
      filter->low_samples = 0U;
      filter->armed = 1U;
    }
  }

  return 0U;
}

static void ConveyorInputs_Process(void)
{
  uint32_t now = HAL_GetTick();
  GPIO_PinState raw_stop;
  GPIO_PinState raw_start;
  uint8_t stop_event;
  uint8_t start_event;

  if ((uint32_t)(now - last_sample_tick) < INPUT_SAMPLE_MS)
  {
    return;
  }
  last_sample_tick = now;

  raw_stop = HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_0);
  raw_start = HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_1);

  /* 上电期间以及输入未回到双低前，强制保持停止。 */
  if (startup_ready == 0U)
  {
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0, GPIO_PIN_RESET);
    if ((uint32_t)(now - startup_tick) < STARTUP_LOCK_MS)
    {
      return;
    }

    if ((raw_stop == GPIO_PIN_RESET) && (raw_start == GPIO_PIN_RESET))
    {
      if (startup_low_samples < LOW_REARM_SAMPLES)
      {
        startup_low_samples++;
      }
      if (startup_low_samples >= LOW_REARM_SAMPLES)
      {
        startup_ready = 1U;
        stop_filter.armed = 1U;
        start_filter.armed = 1U;
      }
    }
    else
    {
      startup_low_samples = 0U;
    }
    return;
  }

  if ((uint32_t)(now - command_lockout_tick) < COMMAND_LOCKOUT_MS)
  {
    return;
  }

  stop_event = PulseInput_Update(&stop_filter, raw_stop);
  start_event = PulseInput_Update(&start_filter, raw_start);

  /* 停止优先；双路同时触发时保持安全状态。 */
  if (stop_event != 0U)
  {
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0, GPIO_PIN_RESET);
    command_lockout_tick = now;
  }
  else if ((start_event != 0U) &&
           (raw_stop == GPIO_PIN_RESET) &&
           (stop_filter.armed != 0U))
  {
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0, GPIO_PIN_SET);
    command_lockout_tick = now;
  }
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
  /* USER CODE BEGIN 2 */
  /* Safe power-on state: keep the conveyor stopped until PA1 requests start. */
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0, GPIO_PIN_RESET);
  startup_tick = HAL_GetTick();
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    ConveyorInputs_Process();
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

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
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

  /** Enables the Clock Security System
  */
  HAL_RCC_EnableCSS();
}

/* USER CODE BEGIN 4 */
/* 传送带输入由主循环采样处理，不在 EXTI 中断中执行控制动作。 */
/* USER CODE END 4 */

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
