#!/bin/zsh

project_dir="$(cd "$(dirname "$0")" && pwd)"
service_label="com.izohposbon.bot"
service_source="$project_dir/$service_label.plist"
service_target="/Users/macstore.uz/Library/LaunchAgents/$service_label.plist"
runtime_dir="/Users/macstore.uz/Library/Application Support/IzohPosbon"
user_domain="gui/$(/usr/bin/id -u)"

echo "Izoh Posbon macOS fon xizmati sozlanmoqda..."
echo

if [[ ! -x "$project_dir/.venv/bin/python" ]]; then
  echo "XATO: Python muhiti topilmadi: $project_dir/.venv/bin/python"
  echo "Oynani yopish uchun istalgan tugmani bosing."
  read -k 1
  exit 1
fi

if [[ ! -f "$service_source" ]]; then
  echo "XATO: Xizmat sozlamasi topilmadi: $service_source"
  echo "Oynani yopish uchun istalgan tugmani bosing."
  read -k 1
  exit 1
fi

# macOS fon jarayonlariga Desktop papkasini o'qishni cheklashi mumkin. Shu sabab
# ishlaydigan nusxa foydalanuvchining Application Support papkasida saqlanadi.
/bin/mkdir -p "$runtime_dir/izoh_posbon" "$runtime_dir/data"
if ! /usr/bin/rsync -a "$project_dir/izoh_posbon/" "$runtime_dir/izoh_posbon/" \
  || ! /bin/cp "$project_dir/.env" "$runtime_dir/.env" \
  || ! /bin/cp "$project_dir/requirements.txt" "$runtime_dir/requirements.txt"; then
  echo "XATO: yangilangan bot fayllarini ishchi papkaga ko'chirib bo'lmadi."
  echo "Oynani yopish uchun istalgan tugmani bosing."
  read -k 1
  exit 1
fi
if [[ ! -x "$runtime_dir/.venv/bin/python" ]]; then
  /bin/mkdir -p "$runtime_dir/.venv"
  if ! /usr/bin/rsync -a "$project_dir/.venv/" "$runtime_dir/.venv/"; then
    echo "XATO: Python muhitini ishchi papkaga ko'chirish amalga oshmadi."
    echo "Oynani yopish uchun istalgan tugmani bosing."
    read -k 1
    exit 1
  fi
fi
if [[ ! -f "$runtime_dir/data/izoh_posbon.db" && -f "$project_dir/data/izoh_posbon.db" ]]; then
  if ! /bin/cp "$project_dir/data/izoh_posbon.db" "$runtime_dir/data/izoh_posbon.db"; then
    echo "XATO: bot ma'lumotlar bazasini ko'chirish amalga oshmadi."
    echo "Oynani yopish uchun istalgan tugmani bosing."
    read -k 1
    exit 1
  fi
fi

/bin/mkdir -p "/Users/macstore.uz/Library/LaunchAgents"
if ! /bin/cp "$service_source" "$service_target"; then
  echo "XATO: macOS fon xizmati faylini o'rnatib bo'lmadi."
  echo "Oynani yopish uchun istalgan tugmani bosing."
  read -k 1
  exit 1
fi

# Nusxa tayyor bo'lgach eski xizmat va qo'lda ochilgan botlarni to'xtatamiz.
/bin/launchctl bootout "$user_domain/$service_label" >/dev/null 2>&1 || true
/usr/bin/pkill -f "Maxsus_Bot/.venv/bin/python -m izoh_posbon" >/dev/null 2>&1 || true
/usr/bin/pkill -f "[.]venv/bin/python -m izoh_posbon" >/dev/null 2>&1 || true

# launchd eski xizmatni ro'yxatdan to'liq chiqarishi uchun biroz vaqt kerak
# bo'lishi mumkin. Aks holda macOS vaqtincha "Bootstrap failed: 5" qaytaradi.
/bin/sleep 2
launch_error_file="/tmp/izohposbon-launchctl-error.log"
service_loaded=false
for attempt in 1 2 3; do
  if /bin/launchctl bootstrap "$user_domain" "$service_target" 2>"$launch_error_file"; then
    service_loaded=true
    break
  fi
  if /bin/launchctl print "$user_domain/$service_label" >/dev/null 2>&1; then
    service_loaded=true
    break
  fi
  /bin/sleep 2
done

if [[ "$service_loaded" != "true" ]]; then
  echo
  /bin/cat "$launch_error_file" 2>/dev/null || true
  echo "XATO: fon xizmatini o'rnatib bo'lmadi. Yuqoridagi xatoni rasmga olib yuboring."
  echo "Oynani yopish uchun istalgan tugmani bosing."
  read -k 1
  exit 1
fi

/bin/launchctl enable "$user_domain/$service_label" >/dev/null 2>&1 || true
/bin/launchctl kickstart -k "$user_domain/$service_label"

/bin/sleep 2
if ! /bin/launchctl print "$user_domain/$service_label" 2>/dev/null | /usr/bin/grep -q "state = running"; then
  echo
  echo "⚠️ Fon xizmati o'rnatildi, lekin bot ishlamayapti. Oxirgi xato:"
  /usr/bin/tail -n 20 "$runtime_dir/data/bot-error.log" 2>/dev/null || true
  echo
  echo "Xatoni rasmga olib yuboring."
  echo "Oynani yopish uchun istalgan tugmani bosing."
  read -k 1
  exit 1
fi

echo
echo "✅ Bot fon xizmatida ishga tushdi."
echo "Terminalni yopishingiz mumkin; bot noutbuk ishlayotganida ishlaydi."
echo "Tizimga qayta kirganda ham bot avtomatik boshlanadi."
echo "Log: $runtime_dir/data/bot.log"
echo
echo "Oynani yopish uchun istalgan tugmani bosing."
read -k 1
