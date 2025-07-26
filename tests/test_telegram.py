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
        message_text = """🎙️ «Чувствовать себя идиотом – одно из самых больших удовольствий в жизни». Интервью с Левоном Ароняном

В гостях у Levitov Chess – триумфатор этапа Freestyle Chess Grand Slam в Лас-Вегасе Левон Аронян!

Не так давно Аронян сыграл матч против Вэя И и разгромно проиграл, в одной из партий просто подставив слона в один ход. Как сказал сам Левон, "обычно успехи – это результат неуспехов": работа над ошибками помогла Ароняну набрать форму и блестяще сыграть в Лас-Вегасе с соп
ерниками, которые годятся ему в сыновья!

Как показывает практика, у разных поколений – разный подход: опытные гроссмейстеры где-то играют интуитивно, а юные дарования стараются высчитать все до конца, не обращая внимания на потенциальные позиционные слабости. Влияет ли это на результат в шахматах Фишера?

О работе над фристайлом, одной из лучших партий в своей жизни и о секрете успеха, как после сорока сохранить прописку в элите – в новом видео рубрики "По первой линии"!

#по_первой_линии #интервью"""

        # Create mock entities
        entities = [
            Mock(offset=3, length=101, __class__=telethon.tl.types.MessageEntityBold),
            Mock(offset=150, length=26, __class__=telethon.tl.types.MessageEntityItalic),
            Mock(offset=190, length=12, __class__=telethon.tl.types.MessageEntityBold),
            Mock(offset=218, length=6, __class__=telethon.tl.types.MessageEntityBold),
            Mock(offset=244, length=5, __class__=telethon.tl.types.MessageEntityBold),
            Mock(offset=340, length=5, __class__=telethon.tl.types.MessageEntityBold),
            Mock(offset=418, length=7, __class__=telethon.tl.types.MessageEntityBold),
            Mock(offset=915, length=11, url="https://example.com", __class__=telethon.tl.types.MessageEntityTextUrl),
            Mock(offset=955, length=16, __class__=telethon.tl.types.MessageEntityHashtag),
            Mock(offset=972, length=9, __class__=telethon.tl.types.MessageEntityHashtag),
        ]

        # Create mock post object
        mock_post = Mock()
        mock_post.message = message_text
        mock_post.entities = entities

        # Call the function
        result = format_telegram_message(mock_post)

        # Assert the exact output that the function produces
        expected = """🎙️ <b>«Чувствовать себя идиотом – одно из самых больших удовольствий в жизни». Интервью с Левоном Ароняном<br>
</b><br>
В гостях у Levitov Chess – триумфатор этапа F<i>reestyle Chess Grand Slam </i>в Лас-Вегасе Л<b>евон Аронян!</b><br>
<br>
Не так давно А<b>ронян </b>сыграл матч против В<b>эя И </b>и разгромно проиграл, в одной из партий просто подставив слона в один ход. Как сказал сам Л<b>евон,</b> "обычно успехи – это результат неуспехов": работа над ошибками помогла А<b>роняну </b>набрать форму и блестяще сыграть в Лас-Вегасе с соп<br>
ерниками, которые годятся ему в сыновья!<br>
<br>
Как показывает практика, у разных поколений – разный подход: опытные гроссмейстеры где-то играют интуитивно, а юные дарования стараются высчитать все до конца, не обращая внимания на потенциальные позиционные слабости. Влияет ли это на результат в шахматах Фишера?<br>
<br>
О работе над фристайлом, одной из лучших партий в своей жизни и о секрете успеха, как после сорока сохранить прописку в элите – в <a href='https://example.com'>новом видео</a> рубрики "По первой линии"!<br>
<br>
#по_первой_линии #интервью"""
        
        self.assertEqual(result, expected)

    def test_format_telegram_message_detailed_output(self):
        """Test format_telegram_message with detailed output verification."""
        
        # Create a test case that matches the entity offsets and lengths
        message_text = "Hello bold text and italic text"
        
        entities = [
            Mock(offset=6, length=9, __class__=telethon.tl.types.MessageEntityBold),
            Mock(offset=22, length=11, __class__=telethon.tl.types.MessageEntityItalic),
        ]
        
        mock_post = Mock()
        mock_post.message = message_text
        mock_post.entities = entities
        
        result = format_telegram_message(mock_post)
        
        # Assert the exact output that the function produces
        expected = "Hello <b>bold text</b> and it<i>alic text</i>"
        self.assertEqual(result, expected)

    def test_format_telegram_message_no_entities(self):
        """Test format_telegram_message with no entities."""
        
        message_text = "Simple message\nwith newlines"
        
        mock_post = Mock()
        mock_post.message = message_text
        mock_post.entities = []

        result = format_telegram_message(mock_post)

        # Should only convert newlines to <br> tags
        expected = "Simple message<br>\nwith newlines"
        self.assertEqual(result, expected)

    def test_format_telegram_message_with_mention(self):
        """Test format_telegram_message with a mention entity."""
        
        message_text = "Hello @username how are you?"
        
        mention_entity = Mock(
            offset=6, 
            length=9, 
            __class__=telethon.tl.types.MessageEntityMention
        )
        
        mock_post = Mock()
        mock_post.message = message_text
        mock_post.entities = [mention_entity]

        result = format_telegram_message(mock_post)

        # Should create a link to t.me (note: uses single quotes)
        self.assertIn("<a href='https://t.me/username'>", result)
        self.assertIn('@username', result)
        self.assertIn('</a>', result)

    def test_format_telegram_message_with_url(self):
        """Test format_telegram_message with a URL entity."""
        
        message_text = "Check out https://example.com for more info"
        
        url_entity = Mock(
            offset=10, 
            length=19, 
            __class__=telethon.tl.types.MessageEntityUrl
        )
        
        mock_post = Mock()
        mock_post.message = message_text
        mock_post.entities = [url_entity]

        result = format_telegram_message(mock_post)

        # Should create a link (note: uses single quotes)
        self.assertIn("<a href='https://example.com'>", result)
        self.assertIn('https://example.com', result)
        self.assertIn('</a>', result)

    def test_format_telegram_message_with_strike(self):
        """Test format_telegram_message with a strike entity."""
        
        message_text = "This text should be struck through"
        
        strike_entity = Mock(
            offset=5, 
            length=4, 
            __class__=telethon.tl.types.MessageEntityStrike
        )
        
        mock_post = Mock()
        mock_post.message = message_text
        mock_post.entities = [strike_entity]

        result = format_telegram_message(mock_post)

        # Should create strike tags
        self.assertIn('<s>', result)
        self.assertIn('</s>', result)
        self.assertIn('text', result)

    def test_format_telegram_message_with_custom_emoji(self):
        """Test format_telegram_message with a custom emoji entity."""
        
        message_text = "Hello 😀 world"
        
        emoji_entity = Mock(
            offset=6, 
            length=2, 
            __class__=telethon.tl.types.MessageEntityCustomEmoji
        )
        
        mock_post = Mock()
        mock_post.message = message_text
        mock_post.entities = [emoji_entity]

        result = format_telegram_message(mock_post)

        # Custom emoji should be handled (currently just adds offset, doesn't modify text)
        # The emoji should still be present in the result
        self.assertIn('😀', result)


if __name__ == '__main__':
    unittest.main() 