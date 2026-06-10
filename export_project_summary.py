import os
from datetime import datetime
from pathlib import Path
import pandas as pd

def get_turkish_month_name(month_num: int) -> str:
    months = {
        1: "january", 2: "february", 3: "march", 4: "april",
        5: "may", 6: "june", 7: "july", 8: "august",
        9: "september", 10: "october", 11: "november", 12: "december"
    }
    return months.get(month_num, "month")

def generate_summary():
    # 1. Günün tarihine uygun dosya adını belirle (Örn: summary_june10.txt)
    now = datetime.now()
    month_name = get_turkish_month_name(now.month)
    output_filename = f"summary_{month_name}{now.day}.txt"
    output_path = Path(output_filename)
    
    project_root = Path(__file__).resolve().parent
    
    # Taranacak uzantılar ve klasörler
    code_extensions = {'.py', '.yaml', '.yml', '.json'}
    data_extensions = {'.csv', '.txt'}
    excluded_dirs = {'__pycache__', '.git', '.pyenv', '.venv', 'logs', 'processed', 'raw'}

    print(f"🔄 Proje haritalandırılıyor ve '{output_filename}' dosyası oluşturuluyor...")

    with open(output_path, "w", encoding="utf-8") as out:
        # === BÖLÜM 1: PROJE KLASÖR YAPISI ===
        out.write("=== PROJE KLASÖR YAPISI ===\n")
        
        def build_tree(dir_path: Path, prefix: str = ""):
            try:
                entries = sorted(list(dir_path.iterdir()), key=lambda x: (x.is_file(), x.name))
                entries = [e for e in entries if e.name not in excluded_dirs and not e.name.startswith('.')]
                
                for i, entry in enumerate(entries):
                    is_last = (i == len(entries) - 1)
                    connector = "└── " if is_last else "├── "
                    out.write(f"{prefix}{connector}{entry.name}\n")
                    
                    if entry.is_dir():
                        next_prefix = prefix + ("    " if is_last else "│   ")
                        build_tree(entry, next_prefix)
            except Exception as e:
                out.write(f"{prefix}[HATA: {e}]\n")

        out.write(".\n")
        build_tree(project_root)
        out.write("\n" + "="*40 + "\n\n")

        # === BÖLÜM 2: DOSYA İÇERİKLERİ VE VERİ ÖZETLERİ ===
        out.write("=== DOSYA İÇERİKLERİ VE VERİ ÖZETLERİ ===\n\n")

        # Projedeki tüm dosyaları sıralı bir şekilde tara
        all_files = sorted(
            [p for p in project_root.rglob('*') if p.is_file() and not any(part in excluded_dirs or part.startswith('.') for part in p.parts)],
            key=lambda x: str(x.relative_to(project_root))
        )

        for file_path in all_files:
            # Bu script'in kendisini çıktıya ekleme
            if file_path == Path(__file__).resolve() or file_path.name == output_filename:
                continue

            rel_path = file_path.relative_to(project_root)
            ext = file_path.suffix.lower()

            out.write("-" * 50 + "\n")
            out.write(f"DOSYA YOLU: ./{rel_path}\n")
            out.write(f"DOSYA TÜRÜ: {ext.upper() if ext else 'Bilinmeyen'}\n")
            out.write("-" * 50 + "\n")

            # Kod Dosyası mı yoksa Veri Dosyası mı kontrol et
            if ext in code_extensions:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    out.write(content if content.strip() else "[Boş Dosya]")
                except Exception as e:
                    out.write(f"[Dosya okunurken hata oluştu: {e}]")
            
            elif ext in data_extensions:
                try:
                    if ext == '.csv':
                        # İlk 5 satırı pandas ile oku
                        df = pd.read_csv(file_path, nrows=5)
                        if df.empty:
                            out.write("[Boş Veri Seti]")
                        else:
                            out.write(f"ℹ️ Veri setinin ilk {len(df)} satırı (Önizleme):\n\n")
                            out.write(df.to_string())
                    else:
                        # Düz metin veri dosyası ise ilk 10 satırını al
                        with open(file_path, "r", encoding="utf-8") as vf:
                            lines = [vf.readline() for _ in range(10)]
                            out.write("".join([l for l in lines if l]))
                except Exception as e:
                    out.write(f"[Veri önizlemesi oluşturulurken hata: {e}]")

            else:
                out.write(f"[Desteklenmeyen dosya türü içerik taramasından muaf tutuldu]")

            out.write("\n\n")

    print(f"✅ İşlem tamamlandı! Rapor kaydedildi: {output_path.resolve()}")

if __name__ == "__main__":
    generate_summary()
