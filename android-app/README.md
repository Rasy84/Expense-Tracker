# Expense Tracker Mobile (Android)

This is a simple Android WebView wrapper around the Flask app.

## Open in Android Studio
1. Open Android Studio.
2. Click "Open" and select the `android-app` folder.
3. Let Gradle sync.

## Configure backend URL
Edit `app/src/main/res/values/strings.xml`:
- Emulator: `http://10.0.2.2:5000`
- Real phone on same Wi-Fi: `http://<your-PC-IP>:5000`

## Run on device
1. Start the Flask server on your PC: `python app.py`
2. Plug in your phone (USB debugging enabled) or start an emulator.
3. Click Run in Android Studio.

## Build APK
- In Android Studio: Build > Build Bundle(s) / APK(s) > Build APK(s)
