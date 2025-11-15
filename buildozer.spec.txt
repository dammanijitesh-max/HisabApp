[app]
title = CylinderApp
package.name = cylinderapp
package.domain = org.jitesh
source.dir = .
source.include_exts = py,kv,png,jpg,db
version = 0.1
requirements = python3,kivy,sqlite3
presplash.filename = assets/presplash.png
icon.filename = assets/icon.png
fullscreen = 0
orientation = portrait

# (VERY IMPORTANT)
# If your main app file is not named main.py, rename it to main.py or change this:
entrypoint = main.py

[buildozer]
log_level = 2

[android]
android.api = 33
ndk_api = 21
# permissions your app may need
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

# (OPTIONAL) Enable keyboard
android.disable_window_transparency = True
android.enable_android_debug_bridge = True

