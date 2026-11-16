
import os
import asyncio
import logging
import requests

from decimal import Decimal, InvalidOperation
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_PAY_API_TOKEN")

API_URL = "https://pay.crypt.bot/api/"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def crypto_request(method, data):
    response = requests.post(
        API_URL + method,
        headers={"Crypto-Pay-API-Token": CRYPTO_TOKEN},
        json=data,
        timeout=20
    )
    response.raise_for_status()
    result = response.json()

    if not result.get("ok"):
        raise Exception(result.get("error", {}).get("name", "Crypto Pay error"))

    return result["result"]


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "💰 Это USDT-платёжный бот.\n\n"
        "Для создания счёта отправь:\n"
        "/pay 10\n\n"
        "Где 10 — сумма в USDT."
    )


@dp.message(Command("pay"))
async def pay(message: Message):
    if not BOT_TOKEN or not CRYPTO_TOKEN:
        await message.answer("Ошибка настроек бота.")
        return

    try:
        parts = message.text.split()

        if len(parts) != 2:
            await message.answer("Используй: /pay 10")
            return

        amount = Decimal(parts[1])

        if not amount.is_finite() or amount <= 0 or amount > 10000:
            await message.answer("Укажи сумму от 0.01 до 10000 USDT.")
            return

        if amount != amount.quantize(Decimal("0.01")):
            await message.answer("Максимум два знака после запятой.")
            return

        invoice = await asyncio.to_thread(
            crypto_request,
            "createInvoice",
            {
                "asset": "USDT",
                "amount": str(amount),
                "description": "Пополнение баланса",
                "payload": f"user:{message.from_user.id}",
                "expires_in": 30
            }
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💳 Оплатить USDT",
                        url=invoice["pay_url"]
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 Проверить оплату",
                        callback_data=f"check:{invoice['invoice_id']}"
                    )
                ]
            ]
        )

        await message.answer(
            f"💰 Счёт создан!\n\n"
            f"Сумма: {amount} USDT\n"
            f"Номер счёта: {invoice['invoice_id']}\n\n"
            f"После оплаты нажми «Проверить оплату».",
            reply_markup=keyboard
        )

    except (InvalidOperation, ValueError):
        await message.answer("Неверная сумма. Пример: /pay 10")

    except Exception as error:
        logging.exception("Payment creation error")
        await message.answer("Не удалось создать счёт. Попробуй позже.")


@dp.callback_query(F.data.startswith("check:"))
async def check_payment(callback: CallbackQuery):
    try:
        invoice_id = callback.data.split(":")[1]

        invoices = await asyncio.to_thread(
            crypto_request,
            "getInvoices",
            {"invoice_ids": invoice_id}
        )

        if not invoices:
            await callback.answer("Счёт не найден.", show_alert=True)
            return

        invoice = invoices[0]

        if invoice.get("payload") != f"user:{callback.from_user.id}":
            await callback.answer("Это не твой счёт.", show_alert=True)
            return

        if invoice.get("status") == "paid":
            await callback.message.answer(
                "✅ Оплата подтверждена!\n"
                f"Сумма: {invoice['amount']} USDT"
            )
            await callback.answer("Оплата успешна!")
        else:
            await callback.answer(
                "Оплата пока не поступила.",
                show_alert=True
            )

    except Exception:
        logging.exception("Payment verification error")
        await callback.answer("Ошибка проверки платежа.", show_alert=True)


async def main():
    if not BOT_TOKEN or not CRYPTO_TOKEN:
        raise RuntimeError("Не заданы BOT_TOKEN или CRYPTO_PAY_API_TOKEN")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
