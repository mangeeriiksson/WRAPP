# Uppdatera och installera nödvändiga paket
sudo apt update && sudo apt upgrade -y
sudo apt install python3-venv

# Kontrollera Python-versionen
python3 --version

# Kontrollera om en gammal virtuell miljö finns och ta bort den
if [ -d "venv" ]; then
    echo "En tidigare virtuell miljö hittades. Tar bort den..."
    rm -rf venv
fi

# Försök skapa den virtuella miljön
echo "Skapar virtuell miljö..."
python3 -m venv venv --copies

if [ $? -ne 0 ]; then
    echo "Misslyckades med att skapa virtuell miljö. Kontrollera ditt system och försök igen."
    exit 1
fi

# Aktivera miljön
echo "Aktiverar den virtuella miljön..."
source venv/bin/activate

# Kontrollera om pip fungerar
echo "Uppdaterar pip..."
pip install --upgrade pip

if [ $? -ne 0 ]; then
    echo "Misslyckades med att uppdatera pip. Kontrollera din installation."
    deactivate
    exit 1
fi

# Installera beroenden om requirements.txt finns
if [ -f "requirements.txt" ]; then
    echo "Installerar beroenden från requirements.txt..."
    pip install -r requirements.txt
else
    echo "Ingen requirements.txt hittades. Skipping dependency installation."
fi

echo "Den virtuella miljön är nu klar att användas!"
