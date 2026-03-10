import asyncio
import time
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from aiogram import Bot
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

# === КОНФИГУРАЦИЯ ===
TELEGRAM_TOKEN = "8751055760:AAHnK7SKaAuMG0pdm4khhoPvXER3gkOt0d0"
CHAT_ID = "-5194619768"
TARGET_URL = "https://profi.ru/backoffice/n.php"
DB_FILE = "seen_orders.json"
CHECK_INTERVAL = 30

LOGIN = os.getenv("PROFI_LOGIN")
PASSWORD = os.getenv("PROFI_PASSWORD")

bot = Bot(token=TELEGRAM_TOKEN)

# === БАЗА ДАННЫХ ===
def load_seen_orders():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_seen_order(order_id):
    seen = load_seen_orders()
    if order_id not in seen:
        seen.append(order_id)
        if len(seen) > 1000:
            seen = seen[-1000:]
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(seen, f)

# === TELEGRAM ===
async def send_to_telegram(title, description, link, is_carousel=False):
    if is_carousel:
        # Карусельный заказ — с пометкой и без звука
        message = (
            f"🔔 **ДОП. ЗАКАЗ**\n\n"
            f"📝 **{title}**\n\n"
            f"{description}\n\n"
            f"🔗 [Открыть заказ]({link})"
        )
        disable_notification = True  # БЕЗ ЗВУКА
    else:
        # Обычный заказ — как обычно
        message = (
            f"🔥 **Новый заказ!**\n\n"
            f"📝 **{title}**\n\n"
            f"{description}\n\n"
            f"🔗 [Открыть заказ]({link})"
        )
        disable_notification = False  # СО ЗВУКОМ
    
    try:
        await bot.send_message(
            chat_id=CHAT_ID, 
            text=message, 
            parse_mode="Markdown",
            disable_notification=disable_notification
        )
        if is_carousel:
            print(f"✅ Отправлено в ТГ (без звука): {title[:50]}")
        else:
            print(f"✅ Отправлено в ТГ: {title[:50]}")
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

# === БРАУЗЕР ===
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Раскомментируй когда всё заработает
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# === ВХОД (ТОЧНО КАК В test_login.py) ===
def login_to_profi(driver):
    print("\n🔐 === ВХОД НА САЙТ ===")
    
    # 1. Открываем сайт
    print(f"🔗 Открываю: {TARGET_URL}")
    driver.get(TARGET_URL)
    time.sleep(5)
    driver.save_screenshot("01_page_loaded.png")
    
    # 2. Вводим логин
    print(f"📱 Ввожу логин: {LOGIN[:3]}***")
    actions = ActionChains(driver)
    actions.send_keys(LOGIN)
    actions.perform()
    time.sleep(1)
    driver.save_screenshot("02_login_entered.png")
    
    # 3. Tab
    print("⌨️ Tab...")
    actions = ActionChains(driver)
    actions.send_keys(Keys.TAB)
    actions.perform()
    time.sleep(1)
    
    # 4. Вводим пароль
    print(f"🔑 Ввожу пароль: {PASSWORD[:3]}***")
    actions = ActionChains(driver)
    actions.send_keys(PASSWORD)
    actions.perform()
    time.sleep(1)
    driver.save_screenshot("03_password_entered.png")
    
    # 5. Enter
    print("🔘 Enter...")
    actions = ActionChains(driver)
    actions.send_keys(Keys.RETURN)
    actions.perform()
    time.sleep(5)
    driver.save_screenshot("04_after_enter.png")
    
    # 6. Проверяем
    print(f"📍 Текущий URL: {driver.current_url}")
    
    if "backoffice" in driver.current_url:
        print("✅ УСПЕХ! Вошёл в личный кабинет!")
        return True
    else:
        print("❌ Не вошёл! Проверь скриншот 04_after_enter.png")
        return False

# === ОБРАБОТКА ОДНОЙ КАРТОЧКИ ===
async def process_card(card, driver, seen_orders, is_carousel=False):
    """Обрабатывает карточку и отправляет в ТГ"""
    
    # === ID ЗАКАЗА ===
    order_id = card.get_attribute("id")
    if not order_id:
        data_testid = card.get_attribute("data-testid")
        if data_testid:
            order_id = data_testid.split("_")[0]
    
    if not order_id:
        return None
    
    if order_id in seen_orders:
        order_type = "карусель" if is_carousel else "обычный"
        print(f"👁 {order_type} заказ {order_id} уже отправлен")
        return None
    
    # === ССЫЛКА ===
    href = card.get_attribute("href")
    if not href:
        return None
    if not href.startswith("http"):
        href = f"https://profi.ru{href}"
    
    # === ЗАГОЛОВОК ===
    try:
        title_el = card.find_element(By.CSS_SELECTOR, "h3[class*='sc-chzmIZ']")
        title = title_el.text.strip()
    except:
        try:
            title_el = card.find_element(By.TAG_NAME, "h3")
            title = title_el.text.strip()
        except:
            title = card.get_attribute("aria-label") or card.text.split('\n')[0].strip()
    
    if not title or len(title) < 5:
        return None
    
    # === ОПИСАНИЕ ===
    try:
        desc_el = card.find_element(By.CSS_SELECTOR, "p[class*='sc-gaeugI']")
        description = desc_el.text.strip()
    except:
        all_text = card.text.strip()
        if title in all_text:
            description = all_text.replace(title, "", 1).strip()
        else:
            lines = all_text.split('\n')[1:]
            description = ' '.join(lines).strip()[:300]
    
    if len(description) > 400:
        description = description[:400] + "..."
    
    # === ОТПРАВКА В TELEGRAM ===
    if is_carousel:
        print(f"🔔 ДОП. заказ #{order_id}: {title[:50]}")
        await send_to_telegram(title, description, href, is_carousel=True)
    else:
        print(f"✨ Новый заказ #{order_id}: {title[:50]}")
        await send_to_telegram(title, description, href, is_carousel=False)
    
    return order_id

# === ПАРСИНГ КАРТОЧЕК ===
async def parse_cards(driver):
    seen_orders = load_seen_orders()
    new_count = 0
    carousel_count = 0
    
    try:
        # Проверяем, есть ли заказы
        if "вы посмотрели все новые заказы" in driver.page_source.lower():
            print("ℹ️ Новых заказов пока нет")
            return 0, 0
        
        # === Ищем ВСЕ карточки ===
        all_cards = driver.find_elements(By.CSS_SELECTOR, "a[data-testid*='order-snippet']")
        print(f"🔍 Всего найдено карточек: {len(all_cards)}")
        
        # === Разделяем на обычные и карусель ===
        regular_cards = []
        carousel_cards = []
        
        for card in all_cards:
            try:
                # Проверяем, находится ли в карусели
                is_in_carousel = driver.execute_script(
                    "return arguments[0].closest('#flatlist-container-CAROUSEL-content') !== null", 
                    card
                )
                
                # Проверяем наличие описания
                has_description = len(card.find_elements(By.CSS_SELECTOR, "p[class*='sc-gaeugI']")) > 0
                
                if is_in_carousel and has_description:
                    carousel_cards.append(card)
                elif has_description:
                    regular_cards.append(card)
                    
            except Exception as e:
                print(f"⚠️ Ошибка классификации: {e}")
                continue
        
        print(f"📋 Обычных заказов: {len(regular_cards)}")
        print(f"🔔 Карусельных заказов: {len(carousel_cards)}")
        
        # === Обрабатываем ОБЫЧНЫЕ заказы (со звуком) ===
        for card in regular_cards:
            try:
                result = await process_card(card, driver, seen_orders, is_carousel=False)
                if result:
                    order_id = result
                    save_seen_order(order_id)
                    new_count += 1
            except Exception as e:
                print(f"⚠️ Ошибка обычной карточки: {e}")
                continue
        
        # === Обрабатываем КАРУСЕЛЬНЫЕ заказы (без звука) ===
        for card in carousel_cards:
            try:
                result = await process_card(card, driver, seen_orders, is_carousel=True)
                if result:
                    order_id = result
                    save_seen_order(order_id)
                    carousel_count += 1
            except Exception as e:
                print(f"⚠️ Ошибка карусельной карточки: {e}")
                continue
    
    except Exception as e:
        print(f"❌ Ошибка парсинга: {e}")
        driver.save_screenshot("parse_error.png")
    
    return new_count, carousel_count

# === ГЛАВНЫЙ ЦИКЛ ===
async def main():
    print("🚀 Запуск парсера Profi.ru...")
    print("📝 Логин:", LOGIN[:3] if LOGIN else "НЕ ЗАДАН")
    print("📝 Пароль:", PASSWORD[:3] if PASSWORD else "НЕ ЗАДАН")
    
    driver = get_driver()
    
    try:
        # ВСЕГДА входим по логину/паролю (КАЖДЫЙ РАЗ!)
        if not login_to_profi(driver):
            print("❌ Не удалось войти. Остановка.")
            return
        
        # Главный цикл
        while True:
            print(f"\n⏰ [{time.strftime('%H:%M:%S')}] Проверка заказов...")
            new_orders, carousel_orders = await parse_cards(driver)
            
            if new_orders > 0:
                print(f"🎉 Обычных заказов: {new_orders}")
            if carousel_orders > 0:
                print(f"🔔 Карусельных заказов: {carousel_orders}")
            if new_orders == 0 and carousel_orders == 0:
                print("💤 Новых заказов нет")
            
            print(f"💤 Обновление через {CHECK_INTERVAL} сек...")
            await asyncio.sleep(CHECK_INTERVAL)
            
            # Просто обновляем страницу (без повторного входа!)
            driver.refresh()
            time.sleep(2)
    
    except KeyboardInterrupt:
        print("\n🛑 Остановка по команде пользователя")
    except Exception as e:
        print(f"💥 Ошибка: {e}")
        driver.save_screenshot("crash.png")
    finally:
        driver.quit()
        print("👋 Браузер закрыт")

if __name__ == "__main__":
    asyncio.run(main())