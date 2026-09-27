#include "lcd2004.h"
#include "i2c1_bus.h"

/* PCF8574 pin -> HD44780 mapping used by the common backpack boards:
 *   P0 = RS, P1 = RW, P2 = EN, P3 = backlight, P4..P7 = D4..D7 */
#define LCD_RS          0x01
#define LCD_EN          0x04
#define LCD_BACKLIGHT   0x08

/* HD44780 commands */
#define LCD_CMD_CLEAR           0x01
#define LCD_CMD_ENTRY_MODE      0x06 /* increment cursor, no display shift */
#define LCD_CMD_DISPLAY_ON      0x0C /* display on, cursor off, blink off */
#define LCD_CMD_FUNCTION_4BIT   0x28 /* 4-bit bus, 2 lines, 5x8 font */
#define LCD_CMD_SET_DDRAM       0x80

/* A 20x4 panel is wired as two 40-char HD44780 lines, each split in half:
 * rows 2 and 3 are the second halves of rows 0 and 1 in DDRAM. */
static const uint8_t row_offsets[LCD2004_ROWS] = { 0x00, 0x40, 0x14, 0x54 };

static void (*lcd_delay_ms)(uint32_t ms);

/* The HD44780 latches data on EN's falling edge, so each nibble is sent as
 * two PCF8574 writes - EN high, then EN low. Sending both bytes (and both
 * nibbles of a full byte) in one I2C transaction keeps it to a single bus
 * access per LCD byte. At 100 kHz each PCF8574 byte takes ~90 us, which
 * already covers the EN pulse width and the 37 us command execution time. */
static int lcd_send_byte(uint8_t value, uint8_t mode)
{
  uint8_t hi = (value & 0xF0) | mode | LCD_BACKLIGHT;
  uint8_t lo = (uint8_t)((value << 4) & 0xF0) | mode | LCD_BACKLIGHT;
  uint8_t frame[4] = { hi | LCD_EN, hi, lo | LCD_EN, lo };

  return I2C1_Transmit(LCD2004_I2C_ADDR, frame, sizeof(frame));
}

/* Used only during init, while the controller may still be in 8-bit mode
 * and only looks at the upper nibble of each write. */
static int lcd_send_nibble(uint8_t nibble)
{
  uint8_t bits = (uint8_t)((nibble << 4) & 0xF0) | LCD_BACKLIGHT;
  uint8_t frame[2] = { bits | LCD_EN, bits };

  return I2C1_Transmit(LCD2004_I2C_ADDR, frame, sizeof(frame));
}

static int lcd_command(uint8_t cmd)
{
  return lcd_send_byte(cmd, 0);
}

/* Power-on reset sequence from the HD44780 datasheet ("initializing by
 * instruction", 4-bit interface): three 0x3 nibbles force a known 8-bit
 * state whatever mode the controller woke up in, then 0x2 switches to
 * 4-bit mode. */
int LCD2004_Init(void (*delay_ms)(uint32_t ms))
{
  lcd_delay_ms = delay_ms;

  if (I2C1_Init() != 0)
  {
    return -1;
  }

  lcd_delay_ms(50); /* > 40 ms after Vcc rises to 2.7 V */

  if (lcd_send_nibble(0x03) != 0)
  {
    return -1; /* nothing acknowledged at this address */
  }
  lcd_delay_ms(5);  /* > 4.1 ms */
  lcd_send_nibble(0x03);
  lcd_delay_ms(1);  /* > 100 us */
  lcd_send_nibble(0x03);
  lcd_delay_ms(1);
  lcd_send_nibble(0x02);
  lcd_delay_ms(1);

  if (lcd_command(LCD_CMD_FUNCTION_4BIT) != 0 ||
      lcd_command(LCD_CMD_DISPLAY_ON) != 0 ||
      lcd_command(LCD_CMD_ENTRY_MODE) != 0)
  {
    return -1;
  }

  return LCD2004_Clear();
}

int LCD2004_Clear(void)
{
  int status = lcd_command(LCD_CMD_CLEAR);
  lcd_delay_ms(2); /* clear takes 1.52 ms, far longer than other commands */
  return status;
}

int LCD2004_WriteLine(uint8_t row, const char *text)
{
  if (row >= LCD2004_ROWS)
  {
    return -1;
  }

  if (lcd_command(LCD_CMD_SET_DDRAM | row_offsets[row]) != 0)
  {
    return -1;
  }

  for (uint8_t col = 0; col < LCD2004_COLS; col++)
  {
    char ch = (*text != '\0') ? *text++ : ' ';
    if (lcd_send_byte((uint8_t)ch, LCD_RS) != 0)
    {
      return -1;
    }
  }

  return 0;
}
