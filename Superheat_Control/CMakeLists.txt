cmake_minimum_required(VERSION 3.22)

#
# This file is generated only once,
# and is not re-generated if converter is called multiple times.
#
# User is free to modify the file as much as necessary
#

# Setup compiler settings
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS ON)


# Define the build type
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Debug")
endif()

# Set the project name
set(CMAKE_PROJECT_NAME Superheat_Control)

# Enable compile command to ease indexing with e.g. clangd
set(CMAKE_EXPORT_COMPILE_COMMANDS TRUE)

# Core project settings
project(${CMAKE_PROJECT_NAME})
message("Build type: " ${CMAKE_BUILD_TYPE})

# Enable CMake support for ASM and C languages
enable_language(C ASM)

# Create an executable object type
add_executable(${CMAKE_PROJECT_NAME})

# Add STM32CubeMX generated sources
add_subdirectory(cmake/stm32cubemx)

# Link directories setup
target_link_directories(${CMAKE_PROJECT_NAME} PRIVATE
    # Add user defined library search paths
)

# Add sources to executable
target_sources(${CMAKE_PROJECT_NAME} PRIVATE
    # Add user sources here
    Core/Src/pid.c
    Core/Src/plant.c
    Core/Src/bme280.c
    Core/Src/i2c1_bus.c
    Core/Src/lcd2004.c
    Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c.c
    Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c_ex.c
)

# I2C1 (PB8/PB9) drives the LCD and, optionally, the BME280. It isn't enabled
# in the .ioc, so the HAL I2C module is switched on here rather than in
# stm32f4xx_hal_conf.h, which CubeMX regenerates.
target_compile_definitions(stm32cubemx INTERFACE HAL_I2C_MODULE_ENABLED)

# BME280 bus selection: configure with -DBME280_BUS=I2C to read the sensor
# over the shared I2C1 bus instead of SPI1. The driver in bme280.c is the same
# for both; only the bus file changes.
set(BME280_BUS "SPI" CACHE STRING "Bus used to talk to the BME280 (SPI or I2C)")
set_property(CACHE BME280_BUS PROPERTY STRINGS SPI I2C)
message("BME280 bus: " ${BME280_BUS})

if(BME280_BUS STREQUAL "I2C")
    target_sources(${CMAKE_PROJECT_NAME} PRIVATE
        Core/Src/bme280_bus_i2c.c
    )
elseif(BME280_BUS STREQUAL "SPI")
    target_sources(${CMAKE_PROJECT_NAME} PRIVATE
        Core/Src/bme280_bus_spi.c
    )
else()
    message(FATAL_ERROR "BME280_BUS must be SPI or I2C, got '${BME280_BUS}'")
endif()

# Add include paths
target_include_directories(${CMAKE_PROJECT_NAME} PRIVATE
    # Add user defined include paths
)

# Add project symbols (macros)
target_compile_definitions(${CMAKE_PROJECT_NAME} PRIVATE
    # Add user defined symbols
)

# Remove wrong libob.a library dependency when using cpp files
list(REMOVE_ITEM CMAKE_C_IMPLICIT_LINK_LIBRARIES ob)

# Add linked libraries
target_link_libraries(${CMAKE_PROJECT_NAME}
    stm32cubemx

    # Add user defined libraries
)

# Enable float support in newlib-nano's printf/scanf
target_link_options(${CMAKE_PROJECT_NAME} PRIVATE
    "-Wl,-u,_printf_float"
    "-Wl,-u,_scanf_float"
)
