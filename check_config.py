"""
Скрипт для проверки и исправления файла конфигурации files_config.json
"""
import json
import os

CONFIG_FILE = "files_config.json"

def check_and_fix_config():
    """Проверка и исправление конфигурации"""
    
    if not os.path.exists(CONFIG_FILE):
        print("✅ Файл конфигурации не найден. Создаём пустой...")
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
        print("✅ Создан пустой файл конфигурации")
        return
    
    print(f"🔍 Проверяем файл: {CONFIG_FILE}")
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print(f"📊 Найдено файлов: {len(config)}")
        
        if not config:
            print("⚠️ Конфигурация пустая - это нормально, если вы ещё не добавили файлы")
            return
        
        # Проверяем каждый файл
        errors_found = False
        for file_id, file_data in config.items():
            print(f"\n📦 Файл ID: {file_id}")
            
            # Проверяем обязательные поля
            required_fields = ['name', 'file_id']
            for field in required_fields:
                if field not in file_data or not file_data[field]:
                    print(f"   ❌ Отсутствует поле: {field}")
                    errors_found = True
                else:
                    print(f"   ✅ {field}: {file_data[field][:50]}...")
            
            # Проверяем опциональные поля
            optional_fields = {
                'file_name': 'Имя файла',
                'description': 'Описание',
                'cover_file_id': 'Обложка',
                'channels': 'Каналы',
                'repost_required': 'Репост'
            }
            
            for field, name in optional_fields.items():
                if field in file_data:
                    value = file_data[field]
                    if field == 'channels':
                        print(f"   ℹ️ {name}: {len(value)} шт.")
                    elif field == 'repost_required':
                        print(f"   ℹ️ {name}: {'Да' if value else 'Нет'}")
                    else:
                        print(f"   ℹ️ {name}: есть")
        
        if errors_found:
            print("\n⚠️ НАЙДЕНЫ ОШИБКИ В КОНФИГУРАЦИИ!")
            print("Рекомендуется удалить files_config.json и добавить файлы заново через /admin")
        else:
            print("\n✅ Конфигурация корректна!")
            
    except json.JSONDecodeError as e:
        print(f"❌ ОШИБКА: Файл повреждён (неверный JSON)")
        print(f"Детали: {e}")
        print("\nРекомендация: Удалите files_config.json и начните заново")
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("🔧 ПРОВЕРКА КОНФИГУРАЦИИ БОТА")
    print("=" * 60)
    check_and_fix_config()
    print("=" * 60)
    input("\nНажмите Enter для выхода...")
