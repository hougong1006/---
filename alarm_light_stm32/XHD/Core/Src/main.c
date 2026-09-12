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

typedef enum
{
  INDICATOR_OFF = 0,
  INDICATOR_RUNNING,
  INDICATOR_DEFECT,
  INDICATOR_INVALID
} IndicatorMode;

typedef struct
{
  uint8_t score;
  GPIO_PinState stable_state;
} LevelFilter;

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/*
 * 独立报警灯控制板信号定义：
 * PA0 <- Jetson GPIO01（传送带正常运行状态）
 * PA1 <- Jetson GPIO07（检测到缺陷件并进入夹取流程）
 * PB0 -> 1号继电器（绿灯）
 * PB1 -> 2号继电器（红灯）
 * PB10 -> 3号继电器（蜂鸣器）
 */
#define CONVEYOR_RUN_INPUT_PIN  GPIO_PIN_0
#define DEFECT_GRAB_INPUT_PIN   GPIO_PIN_1

#define RELAY_GREEN_PIN         GPIO_PIN_0
#define RELAY_RED_PIN           GPIO_PIN_1
#define RELAY_BUZZER_PIN        GPIO_PIN_10
#define RELAY_ALL_PINS          (RELAY_GREEN_PIN | RELAY_RED_PIN | \
                                 RELAY_BUZZER_PIN)

/* 默认按高电平触发继电器编写；若实测为低电平触发，交换这两个定义。 */
#define RELAY_ON_LEVEL      GPIO_PIN_SET
#define RELAY_OFF_LEVEL     GPIO_PIN_RESET

#define STATUS_SCAN_TIME_MS       10U
#define RUN_CONFIRM_SAMPLES       60U  /* 运行编码连续稳定600 ms才生效 */
#define DEFECT_CONFIRM_SAMPLES    80U  /* 缺陷编码连续稳定800 ms才报警 */
#define OFF_CONFIRM_SAMPLES       80U  /* 双低连续稳定800 ms才全部关闭 */
#define STARTUP_LOCK_MS           2000U
#define STARTUP_LOW_SAMPLES       50U  /* 解锁前要求双低稳定500 ms */
#define INPUT_FILTER_MAX          8U
#define INPUT_FILTER_HIGH         6U   /* 输入连续约60 ms才认定为高 */
#define INPUT_FILTER_LOW          2U   /* 输入连续约20 ms才认定为低 */
#define MODE_HOLD_MS              400U

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */

static IndicatorMode current_indicator_mode = INDICATOR_OFF;
static IndicatorMode pending_indicator_mode = INDICATOR_INVALID;
static uint16_t pending_mode_count = 0U;
static LevelFilter conveyor_run_filter = {0U, GPIO_PIN_RESET};
static LevelFilter defect_grab_filter = {0U, GPIO_PIN_RESET};
static uint32_t startup_tick = 0U;
static uint16_t startup_low_count = 0U;
static uint8_t startup_ready = 0U;
static uint32_t mode_hold_until = 0U;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

static void Relay_AllOff(void)
{
  HAL_GPIO_WritePin(GPIOB, RELAY_ALL_PINS, RELAY_OFF_LEVEL);
}

static void Relay_SetState(GPIO_PinState green,
                           GPIO_PinState red,
                           GPIO_PinState buzzer)
{
  HAL_GPIO_WritePin(GPIOB, RELAY_GREEN_PIN, green);
  HAL_GPIO_WritePin(GPIOB, RELAY_RED_PIN, red);
  HAL_GPIO_WritePin(GPIOB, RELAY_BUZZER_PIN, buzzer);
}

static GPIO_PinState LevelFilter_Update(LevelFilter *filter,
                                        GPIO_PinState raw_state)
{
  if (raw_state == GPIO_PIN_SET)
  {
    if (filter->score < INPUT_FILTER_MAX)
    {
      filter->score++;
    }
  }
  else if (filter->score > 0U)
  {
    filter->score--;
  }

  if (filter->score >= INPUT_FILTER_HIGH)
  {
    filter->stable_state = GPIO_PIN_SET;
  }
  else if (filter->score <= INPUT_FILTER_LOW)
  {
    filter->stable_state = GPIO_PIN_RESET;
  }

  return filter->stable_state;
}

static IndicatorMode Indicator_DecodeInputs(GPIO_PinState conveyor_running,
                                             GPIO_PinState defect_grabbing)
{
  if ((conveyor_running == GPIO_PIN_SET) &&
      (defect_grabbing == GPIO_PIN_RESET))
  {
    return INDICATOR_RUNNING;
  }

  if ((conveyor_running == GPIO_PIN_RESET) &&
      (defect_grabbing == GPIO_PIN_SET))
  {
    return INDICATOR_DEFECT;
  }

  if ((conveyor_running == GPIO_PIN_RESET) &&
      (defect_grabbing == GPIO_PIN_RESET))
  {
    return INDICATOR_OFF;
  }

  /* 双高不是有效命令，通常是串扰或切换毛刺。 */
  return INDICATOR_INVALID;
}

static uint16_t Indicator_ConfirmSamples(IndicatorMode mode)
{
  if (mode == INDICATOR_DEFECT)
  {
    return DEFECT_CONFIRM_SAMPLES;
  }

  if (mode == INDICATOR_RUNNING)
  {
    return RUN_CONFIRM_SAMPLES;
  }

  return OFF_CONFIRM_SAMPLES;
}

static void Indicator_ApplyMode(IndicatorMode mode)
{
  if (mode == current_indicator_mode)
  {
    return;
  }

  if (mode == INDICATOR_DEFECT)
  {
    Relay_SetState(RELAY_OFF_LEVEL, RELAY_ON_LEVEL, RELAY_ON_LEVEL);
  }
  else if (mode == INDICATOR_RUNNING)
  {
    Relay_SetState(RELAY_ON_LEVEL, RELAY_OFF_LEVEL, RELAY_OFF_LEVEL);
  }
  else
  {
    Relay_AllOff();
  }

  current_indicator_mode = mode;
  mode_hold_until = HAL_GetTick() + MODE_HOLD_MS;
}

static void Indicator_Update(void)
{
  GPIO_PinState raw_conveyor_running;
  GPIO_PinState raw_defect_grabbing;
  GPIO_PinState conveyor_running;
  GPIO_PinState defect_grabbing;
  IndicatorMode sampled_mode;
  uint16_t required_samples;
  uint32_t now = HAL_GetTick();

  raw_conveyor_running = HAL_GPIO_ReadPin(GPIOA, CONVEYOR_RUN_INPUT_PIN);
  raw_defect_grabbing = HAL_GPIO_ReadPin(GPIOA, DEFECT_GRAB_INPUT_PIN);

  /* 上电先保持安全状态，并等待两路输入回到双低后再解锁。 */
  if (startup_ready == 0U)
  {
    Relay_AllOff();
    current_indicator_mode = INDICATOR_OFF;
    pending_indicator_mode = INDICATOR_INVALID;
    pending_mode_count = 0U;

    if ((uint32_t)(now - startup_tick) < STARTUP_LOCK_MS)
    {
      return;
    }

    if ((raw_conveyor_running == GPIO_PIN_RESET) &&
        (raw_defect_grabbing == GPIO_PIN_RESET))
    {
      if (startup_low_count < STARTUP_LOW_SAMPLES)
      {
        startup_low_count++;
      }
      if (startup_low_count >= STARTUP_LOW_SAMPLES)
      {
        startup_ready = 1U;
      }
    }
    else
    {
      startup_low_count = 0U;
    }
    return;
  }

  conveyor_running = LevelFilter_Update(&conveyor_run_filter,
                                        raw_conveyor_running);
  defect_grabbing = LevelFilter_Update(&defect_grab_filter,
                                       raw_defect_grabbing);
  sampled_mode = Indicator_DecodeInputs(conveyor_running, defect_grabbing);

  if ((int32_t)(now - mode_hold_until) < 0)
  {
    return;
  }

  /* 无效双高或任何采样跳变都会取消本轮确认，并保持现有输出。 */
  if (sampled_mode == INDICATOR_INVALID)
  {
    pending_indicator_mode = INDICATOR_INVALID;
    pending_mode_count = 0U;
    return;
  }

  if (sampled_mode == current_indicator_mode)
  {
    pending_indicator_mode = INDICATOR_INVALID;
    pending_mode_count = 0U;
    return;
  }

  if (sampled_mode != pending_indicator_mode)
  {
    pending_indicator_mode = sampled_mode;
    pending_mode_count = 1U;
    return;
  }

  required_samples = Indicator_ConfirmSamples(sampled_mode);
  if (pending_mode_count < required_samples)
  {
    pending_mode_count++;
  }

  if (pending_mode_count >= required_samples)
  {
    Indicator_ApplyMode(sampled_mode);
    pending_indicator_mode = INDICATOR_INVALID;
    pending_mode_count = 0U;
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

  /* 上电安全状态：绿灯、红灯和蜂鸣器全部关闭。 */
  Relay_AllOff();
  startup_tick = HAL_GetTick();

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    Indicator_Update();
    HAL_Delay(STATUS_SCAN_TIME_MS);

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
