path="/mnt/c/Users/CashAmerica/OneDrive/Documents/Brown-family/40DTU/Meals"
read -p "Enter file/script to transfer from $path: " code
cp "$path/$code" .
echo "Transfer completed"
