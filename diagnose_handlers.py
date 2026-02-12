"""
Диагностический скрипт для проверки порядка обработчиков
"""
import re

def check_handlers():
    """Проверка порядка регистрации обработчиков"""
    
    with open('bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем все обработчики @dp
    pattern = r'@dp\.(message|callback_query)\((.*?)\)\s*\nasync def (\w+)'
    handlers = re.findall(pattern, content, re.MULTILINE)
    
    print("=" * 80)
    print("ПОРЯДОК РЕГИСТРАЦИИ ОБРАБОТЧИКОВ")
    print("=" * 80)
    
    photo_handlers = []
    
    for i, (handler_type, filter_text, func_name) in enumerate(handlers, 1):
        print(f"\n{i}. @dp.{handler_type}({filter_text[:50]}...)")
        print(f"   Функция: {func_name}")
        
        if 'F.photo' in filter_text or 'photo' in filter_text.lower():
            photo_handlers.append((i, func_name, filter_text))
            print("   ⚠️ ОБРАБОТЧИК ФОТО!")
    
    print("\n" + "=" * 80)
    print("ОБРАБОТЧИКИ ФОТО (В ПОРЯДКЕ РЕГИСТРАЦИИ)")
    print("=" * 80)
    
    for order, func_name, filter_text in photo_handlers:
        print(f"\n{order}. {func_name}")
        print(f"   Фильтр: {filter_text[:70]}")
        
        if 'AdminStates' in filter_text:
            print("   ✅ FSM обработчик (специфичный)")
        else:
            print("   ⚠️ ОБЩИЙ обработчик (может перехватывать все фото)")
    
    print("\n" + "=" * 80)
    print("АНАЛИЗ")
    print("=" * 80)
    
    if len(photo_handlers) >= 2:
        first_order, first_name, first_filter = photo_handlers[0]
        
        if 'AdminStates' not in first_filter:
            print("\n❌ ПРОБЛЕМА НАЙДЕНА!")
            print(f"   Первый обработчик фото: {first_name} (порядок: {first_order})")
            print("   Это ОБЩИЙ обработчик - он перехватывает все фото!")
            print("\n💡 РЕШЕНИЕ:")
            print("   FSM обработчики должны быть ВЫШЕ общего обработчика")
            print("   ИЛИ добавить проверку состояния в общий обработчик")
        else:
            print("\n✅ Порядок обработчиков правильный")
    
    # Проверяем наличие проверки состояния
    print("\n" + "=" * 80)
    print("ПРОВЕРКА СОСТОЯНИЯ В ОБЩЕМ ОБРАБОТЧИКЕ")
    print("=" * 80)
    
    if 'current_state = await state.get_state()' in content:
        print("✅ Проверка состояния НАЙДЕНА")
        
        # Ищем контекст
        pattern = r'async def handle_screenshot.*?current_state = await state\.get_state\(\)(.*?)return'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            print("\nКод проверки:")
            print("-" * 40)
            lines = match.group(0).split('\n')[:10]
            for line in lines:
                print(line)
    else:
        print("❌ Проверка состояния НЕ НАЙДЕНА!")
        print("   Добавьте в handle_screenshot:")
        print("""
    current_state = await state.get_state()
    if current_state is not None:
        return
        """)

if __name__ == "__main__":
    try:
        check_handlers()
    except FileNotFoundError:
        print("❌ Файл bot.py не найден в текущей директории!")
        print("Запустите скрипт из папки с bot.py")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    input("\nНажмите Enter для выхода...")
