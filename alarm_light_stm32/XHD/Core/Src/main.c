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

typedef struct
{
  GPIO_PinState stable_state;
  uint16_t high_count;
  uint16_t low_count;
} DebouncedInput;

typedef enum
{
  INDICATOR_OFF = 0,
  INDICATOR_RUNNING,
  INDICATOR_DEFECT
} IndicatorMode;

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
#define RUN_ASSERT_SAMPLES        20U  /* 连续高200 ms才确认正常运行 */
#define RUN_RELEASE_SAMPLES       20U  /* 连续低200 ms才撤销正常运行 */
#define DEFECT_ASSERT_SAMPLES     10U  /* 连续高100 ms才进入报警 */
#define DEFECT_RELEASE_SAMPLES    30U  /* 连续低300 ms才解除报警 */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */

static DebouncedInput conveyor_run_input = {GPIO_PIN_RESET, 0U, 0U};
static DebouncedInput defect_grab_input = {GPIO_PIN_RESET, 0U, 0U};
static IndicatorMode current_indicator_mode = INDICATOR_OFF;

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

static GPIO_PinState Debounce_Update(DebouncedInput *input,
                                      GPIO_PinState raw_state,
                                      uint16_t assert_samples,
                                      uint16_t release_samples)
{
  if (raw_state == GPIO_PIN_SET)
  {
    input->low_count = 0U;
    if (input->stable_state == GPIO_PIN_RESET)
    {
      if (++input->high_count >= assert_samples)
      {
        input->stable_state = GPIO_PIN_SET;
        input->high_count = 0U;
      }
    }
    else
    {
      input->high_count = 0U;
    }
  }
  else
  {
    input->high_count = 0U;
    if (input->stable_state == GPIO_PIN_SET)
    {
      if (++input->low_count >= release_samples)
      {
        input->stable_state = GPIO_PIN_RESET;
        input->low_count = 0U;
      }
    }
    else
    {
      input->low_count = 0U;
    }
  }

  return input->stable_state;
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
}

static void Indicator_Update(void)
{
  GPIO_PinState raw_conveyor_running;
  GPIO_PinState raw_defect_grabbing;
  GPIO_PinState conveyor_running;
  GPIO_PinState defect_grabbing;

  raw_conveyor_running = HAL_GPIO_ReadPin(GPIOA, CONVEYOR_RUN_INPUT_PIN);
  raw_defect_grabbing = HAL_GPIO_ReadPin(GPIOA, DEFECT_GRAB_INPUT_PIN);

  conveyor_running = Debounce_Update(&conveyor_run_input,
                                      raw_conveyor_running,
                                      RUN_ASSERT_SAMPLES,
                                      RUN_RELEASE_SAMPLES);
  defect_grabbing = Debounce_Update(&defect_grab_input,
                                     raw_defect_grabbing,
                                     DEFECT_ASSERT_SAMPLES,
                                     DEFECT_RELEASE_SAMPLES);

  /* 消抖后的报警状态优先，防止两个输入同时为高时绿灯与红灯同时亮。 */
  if (defect_grabbing == GPIO_PIN_SET)
  {
    Indicator_ApplyMode(INDICATOR_DEFECT);
  }
  else if (conveyor_running == GPIO_PIN_SET)
  {
    Indicator_ApplyMode(INDICATOR_RUNNING);
  }
  else
  {
    Indicator_ApplyMode(INDICATOR_OFF);
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
