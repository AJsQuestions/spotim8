# 📱 Spotim8 iOS App

A minimal Spotify library explorer and playlist automator for iPhone. Browse your music library, view playlists and artists, and trigger sync automation from your phone.

## 🚀 Quick Start Summary

1. **Start the server** (on your Mac):
   ```bash
   cd /Users/aryamaan/Desktop/Projects/spotim8
   source venv/bin/activate
   pip install flask flask-cors
   python server/server.py
   ```
   Note the IP address shown (e.g., `http://192.168.1.252:5001`)

2. **Create Xcode project** (see Part 2 below):
   - Open Xcode → Create new iOS App project
   - Add all source files from `apps/ios/Spotim8/`
   - Configure signing with your Apple ID
   - Connect iPhone and build (`⌘R`)

3. **Configure app**:
   - Open app on iPhone → Settings → Enter server IP → Test connection

**📖 For detailed step-by-step instructions, continue reading below.**

## ✨ Features

### 📚 Library Explorer
- **Browse Playlists** - View all your playlists with track counts
- **View Tracks** - See tracks in each playlist with details
- **Browse Artists** - Explore your artists with genres
- **Library Stats** - Overview of your music collection

### 🤖 Playlist Automation
- **Sync Automation** - Trigger full library sync and playlist updates
- **Static Analysis** - Analyze your library and view statistics
- **Real-time Status** - See progress and results as tasks complete

---

## 📋 Prerequisites

Before you begin, make sure you have:

- ✅ **Mac computer** with macOS (for running the server and Xcode)
- ✅ **iPhone** running iOS 15.0 or later
- ✅ **Xcode** installed (version 14.0 or later)
  - Download from the Mac App Store or [developer.apple.com](https://developer.apple.com/xcode/)
- ✅ **Apple ID** (free account works for personal development)
- ✅ **Spotim8 project** set up with `.env` file configured
- ✅ **Python virtual environment** activated with all dependencies installed

---

## 🏗️ Part 1: Server Setup

The iOS app connects to a Python server running on your Mac. Set this up first.

### Step 1.1: Install Server Dependencies

1. **Open Terminal** on your Mac

2. **Navigate to the project:**
   ```bash
   cd /Users/aryamaan/Desktop/Projects/spotim8
   ```

3. **Activate virtual environment:**
   ```bash
   source venv/bin/activate
   ```
   You should see `(venv)` in your terminal prompt.

4. **Install server dependencies:**
   ```bash
   pip install flask flask-cors
   ```
   
   Or from requirements file:
   ```bash
   cd server
   pip install -r requirements.txt
   cd ..
   ```

### Step 1.2: Verify .env File

1. **Check `.env` file exists:**
   ```bash
   ls -la .env
   ```

2. **Verify Spotify credentials:**
   ```bash
   cat .env | grep SPOTIPY_CLIENT
   ```
   
   Should show:
   ```
   SPOTIPY_CLIENT_ID=your_client_id_here
   SPOTIPY_CLIENT_SECRET=your_client_secret_here
   ```

3. **If missing, create it:**
   ```bash
   cp env.example .env
   ```
   Then edit `.env` with your credentials.

### Step 1.3: Start the Server

1. **Start the server:**
   ```bash
   python server/server.py
   ```

2. **Look for output like this:**
   ```
   ============================================================
   Spotim8 iOS Server
   ============================================================
   Server starting on http://0.0.0.0:5001
   Local IP: http://192.168.1.252:5001
   Project root: /Users/aryamaan/Desktop/Projects/spotim8
   ============================================================
   ```

3. **📝 IMPORTANT: Write down the "Local IP" address** (e.g., `http://192.168.1.252:5001`)
   - You'll need this in the app settings later
   - The IP may change if you reconnect to Wi-Fi

4. **Keep this terminal window open** - server must stay running

### Step 1.4: Test the Server

1. **Open a new terminal window** (keep server running)

2. **Test health endpoint:**
   ```bash
   curl http://localhost:5001/health
   ```
   
   Should return:
   ```json
   {"status":"ok","project_root":"/Users/aryamaan/Desktop/Projects/spotim8"}
   ```

3. **If it works, server is ready!** ✅

---

## 📱 Part 2: iOS App Setup

### Step 2.1: Create New Xcode Project

1. **Open Xcode** on your Mac

2. **Create a new project:**
   - **File** → **New** → **Project** (or press `⌘ShiftN`)
   - Select **iOS** tab at the top
   - Choose **App** template
   - Click **Next**

3. **Configure project:**
   - **Product Name:** `Spotim8`
   - **Team:** Select your Apple ID (or leave blank for now)
   - **Organization Identifier:** `com.yourname` (e.g., `com.aryamaan`)
   - **Bundle Identifier:** Will auto-fill as `com.yourname.Spotim8`
   - **Interface:** **SwiftUI**
   - **Language:** **Swift**
   - ✅ **Uncheck** "Include Tests" (optional, you can add later)
   - Click **Next**

4. **Choose location:**
   - Navigate to: `/Users/aryamaan/Desktop/Projects/spotim8/apps/ios/`
   - **IMPORTANT:** 
     - Uncheck "Create Git repository" (project already has git)
     - The project will be created as `Spotim8/` folder inside `apps/ios/`
     - This is fine - it will be separate from the source files in `apps/ios/Spotim8/`
   - Click **Create**

5. **Wait for Xcode to create the project** and finish indexing

### Step 2.2: Add Source Files to Project

1. **Delete the default ContentView.swift:**
   - In Project Navigator (left sidebar), find `ContentView.swift`
   - Right-click → **Delete**
   - Choose **Move to Trash** (not just Remove Reference)

2. **Add all source files:**
   - Right-click on the **blue `Spotim8` folder** in Project Navigator
   - Select **Add Files to "Spotim8"...**
   - Navigate to: `/Users/aryamaan/Desktop/Projects/spotim8/apps/ios/Spotim8/`
   - Select **ALL** of the following:
     - `Spotim8App.swift`
     - `Views/` folder (entire folder)
     - `Services/` folder (entire folder)
     - `Models/` folder (entire folder)
     - `Assets.xcassets` folder (entire folder)
     - `Info.plist`
   - **IMPORTANT:** Configure these options:
     - ✅ **Check** "Copy items if needed"
     - ✅ **Check** "Create groups" (NOT "Create folder references")
     - ✅ **Check** "Add to targets: Spotim8"
   - Click **Add**

3. **Verify project structure:**
   - In Project Navigator, you should now see:
   ```
   Spotim8
   ├── Spotim8App.swift
   ├── Views/
   │   ├── MainView.swift
   │   ├── LibraryView.swift
   │   ├── AutomationView.swift
   │   ├── PlaylistDetailView.swift
   │   └── SettingsView.swift
   ├── Services/
   │   ├── AutomationService.swift
   │   └── LibraryService.swift
   ├── Models/
   │   └── LibraryModels.swift
   ├── Assets.xcassets
   └── Info.plist
   ```

4. **Update Spotim8App.swift:**
   - Open `Spotim8App.swift` in Xcode
   - Replace the entire file content with:
   ```swift
   import SwiftUI

   @main
   struct Spotim8App: App {
       var body: some Scene {
           WindowGroup {
               MainView()
           }
       }
   }
   ```
   - Save the file (`⌘S`)

### Step 2.3: Configure Project Settings

1. **Click the blue project icon** at the top of Project Navigator (labeled "Spotim8")

2. **Select the "Spotim8" target** (under TARGETS, not PROJECT)

3. **General Tab:**
   - **Display Name:** `Spotim8`
   - **Bundle Identifier:** Should be `com.yourname.Spotim8` (change if needed)
   - **Version:** `1.0`
   - **Build:** `1`
   - **Minimum Deployments:** Set to **iOS 15.0** or later
   - **Supported Destinations:** ✅ iPhone (iPad is optional)

4. **Signing & Capabilities Tab:**
   - ✅ **Check** "Automatically manage signing"
   - **Team:** Select your Apple ID
     - If you don't see your Apple ID, click **"Add Account..."**
     - Sign in with your Apple ID (free account works for personal development)
     - After signing in, select your team from the dropdown
   - **Bundle Identifier:** Should match what you set earlier
     - If you see an error, change it to something unique like `com.yourname.spotim8`
   - **Provisioning Profile:** Should auto-generate (you'll see "Xcode Managed Profile")

5. **Info Tab:**
   - Verify `Info.plist` is listed
   - If you see "Custom iOS Target Properties", you can leave it as is

6. **Build Settings Tab (optional check):**
   - Search for "Swift Language Version"
   - Should be **Swift 5** or later
   - Search for "iOS Deployment Target"
   - Should be **15.0** or later

### Step 2.3: Configure Signing

1. **Click the blue project icon** (top of navigator)

2. **Select "Spotim8app" target** (under TARGETS)

3. **Go to "Signing & Capabilities" tab**

4. **Configure:**
   - ✅ Check **"Automatically manage signing"**
   - **Team:** Select your Apple ID
     - If missing, click **"Add Account..."** and sign in
     - Free Apple ID works for personal development

5. **Bundle Identifier:**
   - Should auto-fill
   - If error, change to something unique (e.g., `com.aryamaan.spotim8`)

6. **Verify "iOS Deployment Target"** is **15.0** or later

### Step 2.4: Connect iPhone

1. **Unlock your iPhone**
   - Make sure your iPhone is unlocked and on the home screen

2. **Connect iPhone to Mac** via USB cable
   - Use a USB cable that supports data transfer (not just charging)
   - Connect the cable to both devices

3. **Trust the computer (on iPhone):**
   - A popup will appear on your iPhone: **"Trust This Computer?"**
   - Tap **Trust**
   - Enter your iPhone passcode if prompted
   - You may see "Connecting..." briefly

4. **In Xcode - Select your device:**
   - Look at the top toolbar in Xcode
   - Find the device selector (next to the Play ▶️ and Stop ⏹ buttons)
   - It may currently show "Spotim8 > Any iOS Device" or a simulator
   - Click the device selector dropdown
   - You should see your iPhone listed (e.g., "Aryamaan's iPhone")
   - Select your iPhone from the list

5. **If iPhone doesn't appear in the list:**
   - Make sure iPhone is unlocked
   - Try unplugging and reconnecting the USB cable
   - On iPhone: Go to **Settings** → **General** → **VPN & Device Management**
     - If you see your Mac listed, make sure it's trusted
   - In Xcode: **Window** → **Devices and Simulators**
     - Your iPhone should appear in the left sidebar
     - If it shows "Unpaired", click **"Use for Development"**
   - If still not working:
     - Make sure you're using a data cable (not just charging)
     - Try a different USB port on your Mac
     - Restart both devices if needed

### Step 2.5: Build and Install

1. **Select iPhone as build target:**
   - In the top toolbar, the device selector should show your iPhone
   - If it doesn't, select it from the dropdown (see Step 2.4)

2. **Build the project:**
   - Press `⌘B` (or go to **Product** → **Build**)
   - Wait for Xcode to compile
   - You'll see progress in the top status bar: "Building Spotim8..."
   - When complete, you'll see "Build Succeeded" or "Build Failed"

3. **Check for build errors:**
   - If build fails, check the **Issue Navigator** (⚠️ icon in left sidebar)
   - Common issues:
     - **Missing files:** Make sure all Swift files were added in Step 2.2
     - **Signing errors:** Go back to Step 2.3 and verify signing is configured
     - **Swift version:** Should be Swift 5+
   - Fix any errors and rebuild (`⌘B`)

4. **Run the app:**
   - Press `⌘R` (or click the **Play** button ▶️ in top toolbar)
   - Xcode will:
     1. Build the app (if not already built)
     2. Install it on your iPhone
     3. Launch it automatically

5. **On iPhone - Trust the developer (first time only):**
   - When the app launches for the first time, you may see:
     - **"Untrusted Developer"** message
     - Or the app may not open
   - To fix:
     1. On iPhone: Go to **Settings** → **General** → **VPN & Device Management**
     2. Under "Developer App", you'll see your Apple ID/email
     3. Tap on it
     4. Tap **"Trust [Your Apple ID]"**
     5. Confirm by tapping **"Trust"** in the popup
     6. Return to the home screen
     7. Tap the Spotim8 app icon to launch it

6. **Verify the app launches:**
   - The app should open and show the main interface
   - You should see two tabs at the bottom: "Library" and "Automation"
   - If the app crashes, check the Xcode console (bottom panel) for error messages

---

## ⚙️ Part 3: Configure App

### Step 3.1: Open App

1. **App should launch automatically** after installation
2. **If not**, find Spotim8 on iPhone home screen and tap it

### Step 3.2: Configure Server Connection

1. **Tap "Automation" tab** (bottom navigation)

2. **Tap gear icon** (⚙️) in top right → Settings

3. **Enter server URL:**
   ```
   http://192.168.1.252:5001
   ```
   - Use the IP from Step 1.3
   - **Important:** Include `http://`
   - **Important:** Use Mac's IP, not `localhost`

4. **Test connection:**
   - Tap **"Test Connection"**
   - Should see success message
   - Status indicator turns green

5. **Save:**
   - Tap **"Save"**
   - Should show "Connected" status

### Step 3.3: Verify Connection

1. **Go back to Automation tab**

2. **Check status:**
   - Should show "Connected" (green indicator)
   - If "Disconnected", check server URL

3. **Test with Static Analysis:**
   - Tap **"Run Static Analysis"** (fast and safe)
   - Should see status updates
   - Results appear when complete

4. **If this works, you're all set!** 🎉

---

## 🎯 Part 4: Using the App

### Library Tab

**Browse Playlists:**
- Tap any playlist to see tracks
- Scroll to see all playlists

**View Artists:**
- Switch to "Artists" tab at top
- Browse all artists with genres

**Library Stats:**
- View totals at top (playlists, tracks, artists)

**Refresh:**
- Pull down to refresh
- Or tap refresh button

### Automation Tab

**Run Sync Automation:**
- Tap **"Run Sync Automation"**
- Syncs library and updates playlists
- ⚠️ Takes 10-30 minutes for large libraries
- Real-time progress updates

**Run Static Analysis:**
- Tap **"Run Static Analysis"**
- Quick library analysis (< 1 minute)
- Shows statistics

**View Task Status:**
- Real-time progress for running tasks
- Results when tasks complete

---

## 🔍 Troubleshooting

### Server Issues

#### "Cannot connect to server"

1. **Check server is running:**
   - Look at terminal where server started
   - If crashed, restart: `python server/server.py`

2. **Verify IP address:**
   - IP may change if Wi-Fi reconnected
   - Check server terminal output for current IP
   - Update app settings with new IP

3. **Check same network:**
   - Mac and iPhone must be on same Wi-Fi
   - Verify network names match

4. **Test from Mac:**
   ```bash
   curl http://localhost:5001/health
   ```
   Should return: `{"status":"ok",...}`

5. **Test from iPhone Safari:**
   - Open Safari on iPhone
   - Go to: `http://YOUR_MAC_IP:5001/health`
   - Should show JSON response
   - If this works but app doesn't, it's an app config issue

#### "Port already in use"

1. **Find what's using port:**
   ```bash
   lsof -i :5001
   ```

2. **Kill process or use different port:**
   ```bash
   SPOTIM8_SERVER_PORT=5002 python server/server.py
   ```
   Then update app settings with new port.

#### Firewall blocking

1. **On Mac:**
   - **System Settings** → **Network** → **Firewall**
   - Temporarily disable to test
   - Or add Python to allowed apps

2. **Allow connections:**
   - macOS may ask to allow connections when starting server
   - Click **Allow**

### App Issues

#### Xcode project creation issues

**"No such module 'SwiftUI'" or similar errors:**
- Make sure you selected **SwiftUI** as the interface when creating the project
- If you selected UIKit by mistake, create a new project with SwiftUI

**Files not appearing in Project Navigator:**
- Make sure you selected "Create groups" (not "Create folder references") when adding files
- Folder references appear as yellow folders, groups appear as blue folders
- If you see yellow folders, delete them and re-add with "Create groups" checked

**"Cannot find 'MainView' in scope":**
- Make sure you added all files from `apps/ios/Spotim8/Views/` folder
- Check that `MainView.swift` is in the project (should be in Views group)
- Verify target membership: Select the file → Right-click → **Get Info** → Check "Target Membership" includes "Spotim8"

#### App won't build

1. **Clean build:**
   - **Product** → **Clean Build Folder** (`⌘ShiftK`)
   - Wait for cleaning to complete

2. **Check errors:**
   - Open **Issue Navigator** (⚠️ icon in left sidebar)
   - Read each error message carefully
   - Common fixes:
     - **Missing imports:** Add `import SwiftUI` at top of files if missing
     - **File not in target:** Right-click file → **Get Info** → Check "Target Membership"
     - **Syntax errors:** Check for typos or missing closing braces

3. **Verify files:**
   - All Swift files should be in the project
   - Check target membership: Right-click any file → **Get Info** → Verify "Spotim8" is checked under "Target Membership"
   - Make sure `Spotim8App.swift` has `@main` attribute

4. **Check build settings:**
   - Select project → Target "Spotim8" → **Build Settings**
   - Search for "Swift Language Version" → Should be Swift 5
   - Search for "iOS Deployment Target" → Should be 15.0 or later

#### App crashes

1. **Check Xcode console:**
   - Bottom panel in Xcode
   - Read error messages

2. **Check device logs:**
   - **Window** → **Devices and Simulators**
   - Select iPhone → **Open Console**
   - Look for crash logs

3. **Rebuild:**
   - Clean (`⌘ShiftK`) → Build (`⌘B`) → Run (`⌘R`)

#### "Untrusted Developer"

1. **On iPhone:**
   - **Settings** → **General** → **VPN & Device Management**
   - Tap Apple ID → **Trust**

#### No data in Library tab

1. **Run sync first:**
   - Automation tab → **Run Sync Automation**
   - Wait for completion

2. **Check server data:**
   ```bash
   ls -lh data/*.parquet
   ```
   Should see parquet files

3. **Refresh:**
   - Pull down to refresh in Library tab

### Network Issues

#### Can't find server IP

1. **On Mac:**
   ```bash
   ifconfig | grep "inet " | grep -v 127.0.0.1
   ```
   Look for IP starting with `192.168.` or `10.`

2. **Or System Settings:**
   - **System Settings** → **Network** → **Wi-Fi** → **Details**
   - Look for "IP Address"

#### Connection works on Mac but not iPhone

1. **Verify same Wi-Fi:**
   - Both devices on same network
   - Network names match exactly

2. **Test iPhone browser:**
   - Safari → `http://YOUR_MAC_IP:5001/health`
   - If this doesn't work, it's a network issue

---

## 📝 Quick Reference

### Server Commands

```bash
# Start server
cd /Users/aryamaan/Desktop/Projects/spotim8
source venv/bin/activate
python server/server.py

# Test server
curl http://localhost:5001/health

# Use different port
SPOTIM8_SERVER_PORT=5002 python server/server.py

# Kill process on port
lsof -ti:5001 | xargs kill -9
```

### Xcode Shortcuts

- `⌘R` - Build and run
- `⌘B` - Build only
- `⌘ShiftK` - Clean build folder
- `⌘.` - Stop running app
- `⌘O` - Open project

### App Settings

- **Server URL format:** `http://192.168.X.X:5001`
- **Default port:** 5001
- **Connection timeout:** 5 seconds

### Server Endpoints

The app uses these endpoints:

- `GET /health` - Health check
- `GET /library/stats` - Library statistics
- `GET /library/playlists` - List of playlists
- `GET /library/playlist/<id>/tracks` - Tracks in a playlist
- `GET /library/artists` - List of artists
- `POST /sync` - Trigger sync automation
- `POST /analysis` - Trigger static analysis
- `GET /status/<task_id>` - Get task status

---

## ✅ Verification Checklist

Before considering setup complete:

### Server Setup
- [ ] Server starts without errors
- [ ] Server shows local IP address (e.g., `http://192.168.1.252:5001`)
- [ ] `curl http://localhost:5001/health` works and returns JSON
- [ ] Server terminal shows "Server starting on http://0.0.0.0:5001"

### Xcode Project Setup
- [ ] Xcode project created successfully
- [ ] All source files added to project (Spotim8App.swift, Views/, Services/, Models/)
- [ ] Assets.xcassets folder added
- [ ] Info.plist added
- [ ] Project structure visible in Project Navigator (blue folders)
- [ ] No red file icons (missing files) in Project Navigator
- [ ] Build Settings: iOS Deployment Target set to 15.0+
- [ ] Build Settings: Swift Language Version is Swift 5+

### Code Signing
- [ ] Signing & Capabilities: "Automatically manage signing" is checked
- [ ] Team selected (your Apple ID)
- [ ] Bundle Identifier is set (e.g., `com.yourname.Spotim8`)
- [ ] No signing errors in Issue Navigator

### Device Connection
- [ ] iPhone connected via USB
- [ ] iPhone appears in Xcode device selector
- [ ] iPhone selected as build target in Xcode toolbar

### Build & Install
- [ ] App builds successfully (`⌘B` - no errors)
- [ ] App installs on iPhone (no installation errors)
- [ ] App launches on iPhone
- [ ] If "Untrusted Developer" appeared, you trusted it in Settings

### App Functionality
- [ ] App shows two tabs: "Library" and "Automation"
- [ ] Settings accessible (gear icon in Automation tab)
- [ ] Server URL can be entered in Settings
- [ ] "Test Connection" button works
- [ ] Connection status shows "Connected" (green) after entering server URL
- [ ] "Run Static Analysis" works and shows results
- [ ] Library tab shows data (after running sync at least once)

---

## 🎓 Next Steps

Once everything works:

1. **Run your first sync** from the app
2. **Explore your library** in the Library tab
3. **Set up automation** (cron job) for automatic daily syncs
4. **Customize playlist settings** in your `.env` file

---

## 📚 Project Structure

After setup, your project structure should look like this:

```
apps/ios/
├── Spotim8/                    # Source files (original)
│   ├── Spotim8App.swift       # App entry point
│   ├── Views/                 # UI views
│   │   ├── MainView.swift
│   │   ├── LibraryView.swift
│   │   ├── AutomationView.swift
│   │   ├── PlaylistDetailView.swift
│   │   └── SettingsView.swift
│   ├── Services/              # API clients
│   │   ├── AutomationService.swift
│   │   └── LibraryService.swift
│   ├── Models/                # Data models
│   │   └── LibraryModels.swift
│   ├── Assets.xcassets        # App assets
│   └── Info.plist             # App configuration
└── Spotim8/                   # Xcode project (created by Xcode)
    ├── Spotim8.xcodeproj      # Xcode project file
    └── Spotim8/               # Copied source files
        ├── Spotim8App.swift
        ├── Views/
        ├── Services/
        ├── Models/
        ├── Assets.xcassets
        └── Info.plist
```

**Note:** When you create the Xcode project in Step 2.1, Xcode will create a new `Spotim8/` folder. The source files from `apps/ios/Spotim8/` will be copied into the Xcode project folder when you add them in Step 2.2.

---

## 🆘 Still Having Issues?

1. **Check main README.md** for general troubleshooting
2. **Check server/README.md** for server-specific issues
3. **Check Xcode console** for detailed error messages
4. **Verify all prerequisites** are met
5. **Try restarting** both server and app

---

## 📄 Requirements

- iOS 15.0+
- Xcode 14+
- Server running on Mac/computer
- Same Wi-Fi network for Mac and iPhone

---

Enjoy your Spotim8 iOS app! 🎵
