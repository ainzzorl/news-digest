import unittest
from unittest.mock import Mock
import telethon.tl.types
import sys
import os

# Add the project root to the path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from news_digest.core.telegram import format_telegram_message


class TestFormatTelegramMessage(unittest.TestCase):
    def test_format_telegram_message_with_entities(self):
        """Test format_telegram_message with the specified text and entities."""

        # Create mock message text
        message_text = """🎙️Фабиано Каруана: «Я думал, что будет какой-то шепот в зале, в реальности же были вопли»

В нашумевшем видео с критикой серии Freestyle Chess Хикару Накамура упомянул, что его коллега Фабиано Каруана уже выражал схожую позицию в интервью, которое было опубликовано, но позднее странным образом исчезло"""

        # Create mock entities
        entities = [
            Mock(offset=3, length=87, __class__=telethon.tl.types.MessageEntityBold),
            Mock(
                offset=105,
                length=5,
                url="https://youtu.be/pOVsGE1u8Ps",
                __class__=telethon.tl.types.MessageEntityTextUrl,
            ),
            Mock(
                offset=128, length=15, __class__=telethon.tl.types.MessageEntityItalic
            ),
            Mock(offset=144, length=16, __class__=telethon.tl.types.MessageEntityBold),
            Mock(offset=186, length=15, __class__=telethon.tl.types.MessageEntityBold),
        ]

        # Create mock post object
        mock_post = Mock()
        mock_post.message = message_text
        mock_post.entities = entities

        # Call the function
        result = format_telegram_message(mock_post)

        # Assert the exact output that the function produces
        expected = """🎙️<b>Фабиано Каруана: «Я думал, что будет какой-то шепот в зале, в реальности же были вопли»</b><br>
<br>
В нашумевшем <a href='https://youtu.be/pOVsGE1u8Ps'>видео</a> с критикой серии <i>Freestyle Chess</i> <b>Хикару Накамура </b>упомянул, что его коллега <b>Фабиано Каруана</b> уже выражал схожую позицию в интервью, которое было опубликовано, но позднее странным образом исчезло"""

        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
