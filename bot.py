import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from database import get_session, WelcomePost, Review
import config
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Состояния для ConversationHandler
RATING, REVIEW_TEXT, REVIEW_PHOTO = range(3)
WELCOME_TEXT, WELCOME_MEDIA = range(2)


class Bot:
    def __init__(self):
        self.application = Application.builder().token(config.BOT_TOKEN).build()
        self.setup_handlers()

    def is_admin(self, user_id: int) -> bool:
        return user_id in config.ADMIN_IDS

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_id = user.id

        if self.is_admin(user_id):
            # Админ панель
            keyboard = [
                [InlineKeyboardButton("✏️ Изменить приветственный пост", callback_data="edit_welcome")],
                [InlineKeyboardButton("📊 Посмотреть отзывы", callback_data="view_reviews_admin")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "👋 Добро пожаловать в админ панель!",
                reply_markup=reply_markup
            )
        else:
            # Обычный пользователь
            await self.show_welcome_post(update, context)

    async def show_welcome_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        session = get_session()
        try:
            welcome_post = session.query(WelcomePost).filter_by(is_active=True).first()

            keyboard = [
                [InlineKeyboardButton("⭐ Оставить отзыв", callback_data="leave_review")],
                [InlineKeyboardButton("📖 Посмотреть отзывы", callback_data="view_reviews")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if welcome_post:
                if welcome_post.photo:
                    await update.message.reply_photo(
                        photo=welcome_post.photo,
                        caption=welcome_post.text,
                        reply_markup=reply_markup
                    )
                elif welcome_post.video:
                    await update.message.reply_video(
                        video=welcome_post.video,
                        caption=welcome_post.text,
                        reply_markup=reply_markup
                    )
                else:
                    await update.message.reply_text(
                        welcome_post.text,
                        reply_markup=reply_markup
                    )
            else:
                default_text = "👋 Добро пожаловать! Мы рады вас видеть!"
                await update.message.reply_text(
                    default_text,
                    reply_markup=reply_markup
                )
        finally:
            session.close()

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data

        if data == "leave_review":
            await self.start_review_process(query, context)
        elif data == "view_reviews":
            await self.show_reviews(query, context, 0, is_admin=False)
        elif data == "edit_welcome" and self.is_admin(user_id):
            await self.start_edit_welcome(query, context)
        elif data == "view_reviews_admin" and self.is_admin(user_id):
            await self.show_reviews(query, context, 0, is_admin=True)
        elif data.startswith("reviews_page_"):
            page = int(data.split("_")[2])
            is_admin = data.split("_")[3] == "admin"
            await self.show_reviews(query, context, page, is_admin)

    async def start_review_process(self, query, context):
        keyboard = [
            [InlineKeyboardButton(str(i), callback_data=f"rating_{i}") for i in range(1, 6)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "Пожалуйста, выберите оценку от 1 до 5:",
            reply_markup=reply_markup
        )

    async def rating_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        rating = int(query.data.split("_")[1])
        context.user_data['rating'] = rating

        await query.edit_message_text(
            "Теперь напишите текст отзыва. Вы также можете прикрепить фото к отзыву."
        )

        return REVIEW_TEXT

    async def receive_review_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['review_text'] = update.message.text

        keyboard = [
            [InlineKeyboardButton("📷 Прикрепить фото", callback_data="add_photo")],
            [InlineKeyboardButton("✅ Завершить без фото", callback_data="finish_review")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Хотите прикрепить фото к отзыву?",
            reply_markup=reply_markup
        )

        return REVIEW_PHOTO

    async def handle_review_photo_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if query.data == "add_photo":
            await query.edit_message_text("Пожалуйста, отправьте фото:")
            return REVIEW_PHOTO
        else:
            await self.save_review(query, context, None)
            return ConversationHandler.END

    async def receive_review_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            photo_url = photo_file.file_path

            await self.save_review(update, context, photo_url)
            return ConversationHandler.END
        else:
            await update.message.reply_text("Пожалуйста, отправьте фото или нажмите 'Завершить без фото'")
            return REVIEW_PHOTO

    async def save_review(self, update: Update, context: ContextTypes.DEFAULT_TYPE, photo_url: str = None):
        user_data = context.user_data
        user = update.effective_user

        session = get_session()
        try:
            review = Review(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                rating=user_data['rating'],
                text=user_data['review_text'],
                photo=photo_url,
                created_at=datetime.utcnow()
            )
            session.add(review)
            session.commit()

            # Отправляем сообщение в зависимости от типа update
            if hasattr(update, 'message'):
                await update.message.reply_text("✅ Спасибо за ваш отзыв!")
            else:
                await update.callback_query.edit_message_text("✅ Спасибо за ваш отзыв!")

        except Exception as e:
            logging.error(f"Error saving review: {e}")
            if hasattr(update, 'message'):
                await update.message.reply_text("❌ Произошла ошибка при сохранении отзыва.")
            else:
                await update.callback_query.edit_message_text("❌ Произошла ошибка при сохранении отзыва.")
        finally:
            session.close()

        # Очищаем user_data
        context.user_data.clear()

    async def show_reviews(self, query, context, page: int, is_admin: bool):
        session = get_session()
        try:
            reviews = session.query(Review).order_by(Review.created_at.desc()).all()

            if not reviews:
                await query.edit_message_text("📝 Отзывов пока нет.")
                return

            # Пагинация
            per_page = 5
            total_pages = (len(reviews) + per_page - 1) // per_page
            start_idx = page * per_page
            end_idx = start_idx + per_page
            page_reviews = reviews[start_idx:end_idx]

            message_text = "📊 Отзывы:\n\n"

            for i, review in enumerate(page_reviews, start=1):
                stars = "⭐" * review.rating
                if is_admin:
                    user_info = f"👤 {review.first_name or ''} {review.last_name or ''} (@{review.username or 'нет'})"
                    message_text += f"{i + start_idx}. {stars}\n{user_info}\n{review.text}\n"
                else:
                    message_text += f"{i + start_idx}. {stars}\n{review.text}\n"

                if review.photo:
                    message_text += "📷 Есть фото\n"

                message_text += f"📅 {review.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"

            # Кнопки пагинации
            keyboard = []
            if page > 0:
                keyboard.append(InlineKeyboardButton("◀️ Назад",
                                                     callback_data=f"reviews_page_{page - 1}_{'admin' if is_admin else 'user'}"))

            if page < total_pages - 1:
                keyboard.append(InlineKeyboardButton("Вперед ▶️",
                                                     callback_data=f"reviews_page_{page + 1}_{'admin' if is_admin else 'user'}"))

            reply_markup = InlineKeyboardMarkup([keyboard]) if keyboard else None

            await query.edit_message_text(
                message_text,
                reply_markup=reply_markup
            )

        finally:
            session.close()

    # Админ функции
    async def start_edit_welcome(self, query, context):
        await query.edit_message_text(
            "Введите новый текст приветственного поста. Вы также можете прикрепить фото или видео."
        )
        return WELCOME_TEXT

    async def receive_welcome_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['welcome_text'] = update.message.text

        keyboard = [
            [InlineKeyboardButton("📷 Прикрепить фото", callback_data="welcome_photo")],
            [InlineKeyboardButton("🎥 Прикрепить видео", callback_data="welcome_video")],
            [InlineKeyboardButton("✅ Без медиа", callback_data="welcome_no_media")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Хотите прикрепить фото или видео к посту?",
            reply_markup=reply_markup
        )

        return WELCOME_MEDIA

    async def handle_welcome_media_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if query.data == "welcome_photo":
            await query.edit_message_text("Пожалуйста, отправьте фото:")
            context.user_data['media_type'] = 'photo'
        elif query.data == "welcome_video":
            await query.edit_message_text("Пожалуйста, отправьте видео:")
            context.user_data['media_type'] = 'video'
        else:
            await self.save_welcome_post(query, context, None, None)
            return ConversationHandler.END

        return WELCOME_MEDIA

    async def receive_welcome_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_data = context.user_data
        media_type = user_data.get('media_type')

        if media_type == 'photo' and update.message.photo:
            media_file = await update.message.photo[-1].get_file()
            media_url = media_file.file_path
            await self.save_welcome_post(update, context, media_url, 'photo')
        elif media_type == 'video' and update.message.video:
            media_file = await update.message.video.get_file()
            media_url = media_file.file_path
            await self.save_welcome_post(update, context, media_url, 'video')
        else:
            await update.message.reply_text("Пожалуйста, отправьте корректный медиа файл.")
            return WELCOME_MEDIA

        return ConversationHandler.END

    async def save_welcome_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE, media_url: str = None,
                                media_type: str = None):
        user_data = context.user_data

        session = get_session()
        try:
            # Деактивируем старые посты
            session.query(WelcomePost).update({WelcomePost.is_active: False})

            # Создаем новый пост
            welcome_post = WelcomePost(
                text=user_data['welcome_text'],
                photo=media_url if media_type == 'photo' else None,
                video=media_url if media_type == 'video' else None,
                is_active=True
            )
            session.add(welcome_post)
            session.commit()

            success_message = "✅ Приветственный пост успешно обновлен!"
            if hasattr(update, 'message'):
                await update.message.reply_text(success_message)
            else:
                await update.callback_query.edit_message_text(success_message)

        except Exception as e:
            logging.error(f"Error saving welcome post: {e}")
            error_message = "❌ Произошла ошибка при сохранении поста."
            if hasattr(update, 'message'):
                await update.message.reply_text(error_message)
            else:
                await update.callback_query.edit_message_text(error_message)
        finally:
            session.close()

        context.user_data.clear()

    def setup_handlers(self):
        # Обработчик команды /start
        self.application.add_handler(CommandHandler("start", self.start))

        # ConversationHandler для отзывов
        review_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.rating_selected, pattern="^rating_")],
            states={
                RATING: [CallbackQueryHandler(self.rating_selected, pattern="^rating_")],
                REVIEW_TEXT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_review_text)
                ],
                REVIEW_PHOTO: [
                    CallbackQueryHandler(self.handle_review_photo_choice, pattern="^(add_photo|finish_review)$"),
                    MessageHandler(filters.PHOTO, self.receive_review_photo)
                ],
            },
            fallbacks=[],
        )

        # ConversationHandler для редактирования приветственного поста (только для админов)
        welcome_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_edit_welcome, pattern="^edit_welcome$")],
            states={
                WELCOME_TEXT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_welcome_text)
                ],
                WELCOME_MEDIA: [
                    CallbackQueryHandler(self.handle_welcome_media_choice, pattern="^welcome_(photo|video|no_media)$"),
                    MessageHandler(filters.PHOTO | filters.VIDEO, self.receive_welcome_media)
                ],
            },
            fallbacks=[],
        )

        # Обработчики кнопок
        self.application.add_handler(CallbackQueryHandler(self.button_handler,
                                                          pattern="^(leave_review|view_reviews|edit_welcome|view_reviews_admin|reviews_page_)"))

        # Добавляем ConversationHandler
        self.application.add_handler(review_conv)
        self.application.add_handler(welcome_conv)

    def run(self):
        self.application.run_polling()


if __name__ == "__main__":
    bot = Bot()
    bot.run()