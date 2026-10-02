from pathlib import Path
import runpy
import re

# Partimos de la v21: conserva FPS BLAST, colores, logo y telemetría.
runpy.run_path('tools/codm_v21_stability.py', run_name='__main__')

root = Path('CODMCrosshair_Auto')

# Versión
gradle = root / 'app/build.gradle'
s = gradle.read_text().replace('versionCode 21', 'versionCode 22').replace("versionName '21.0'", "versionName '22.0'")
gradle.write_text(s)

# Manifest: retiramos AccessibilityService y pasamos a overlay + Usage Access + FGS.
manifest = root / 'app/src/main/AndroidManifest.xml'
m = manifest.read_text()

permissions = '''    <uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW" />
    <uses-permission android:name="android.permission.PACKAGE_USAGE_STATS" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />

'''
if 'android.permission.SYSTEM_ALERT_WINDOW' not in m:
    m = m.replace('    <application', permissions + '    <application', 1)

# Elimina la declaración del servicio de accesibilidad: ya no se necesita.
m, n = re.subn(
    r'\n\s*<service\s+android:name="\.CodmAccessibilityService".*?</service>\s*',
    '\n',
    m,
    count=1,
    flags=re.S
)
if n != 1:
    raise SystemExit('No se encontró servicio Accessibility en manifest')

overlay_service = '''
        <service
            android:name=".GameOverlayService"
            android:exported="false"
            android:foregroundServiceType="specialUse">
            <property
                android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"
                android:value="Crosshair overlay and local game performance telemetry" />
        </service>

'''
# insertar antes del primer tile service
anchor = '        <service\n            android:name=".CrosshairTileService"'
if anchor not in m:
    raise SystemExit('No se encontró anchor tile en manifest')
m = m.replace(anchor, overlay_service + anchor, 1)
manifest.write_text(m)

# Nuevo servicio independiente de Accesibilidad.
game_service = root / 'app/src/main/java/com/codm/crosshair/GameOverlayService.java'
game_service.write_text(r'''package com.codm.crosshair;

import android.app.AppOpsManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.app.usage.UsageEvents;
import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.Process;
import android.provider.Settings;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.TextView;

import java.util.List;
import java.util.Locale;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class GameOverlayService extends Service {
    public static final String ACTION_TEST = "com.codm.crosshair.TEST";
    public static final String ACTION_UPDATE = "com.codm.crosshair.UPDATE";
    public static final String ACTION_HIDE = "com.codm.crosshair.HIDE";
    public static final String ACTION_ENABLE = "com.codm.crosshair.ENABLE";
    public static final String ACTION_PANEL_MOVE = "com.codm.crosshair.PANEL_MOVE";
    public static final String ACTION_PANEL_LOCK = "com.codm.crosshair.PANEL_LOCK";

    private static final String GLOBAL_PACKAGE = "com.activision.callofduty.shooter";
    private static final String GARENA_PACKAGE = "com.garena.game.codm";
    private static final String CHANNEL_ID = "crosshair_overlay";
    private static final int NOTIFICATION_ID = 22022;

    private WindowManager windowManager;
    private SharedPreferences prefs;
    private CrosshairView crosshairView;
    private WindowManager.LayoutParams params;
    private TextView statsView;
    private WindowManager.LayoutParams statsParams;
    private boolean showing = false;
    private boolean testMode = false;
    private boolean gameSessionActive = false;
    private volatile String currentCodmPackage = GLOBAL_PACKAGE;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable foregroundMonitor = this::monitorForegroundApp;
    private BroadcastReceiver commandReceiver;

    private ScheduledExecutorService statsExecutor;
    private ShizukuFpsClient fpsClient;

    private float panelDragOffsetX;
    private float panelDragOffsetY;
    private float panelDownX;
    private float panelDownY;
    private boolean panelDragged;

    @Override
    public void onCreate() {
        super.onCreate();
        prefs = getSharedPreferences("crosshair", MODE_PRIVATE);
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        createNotificationChannel();
        try {
            startForeground(NOTIFICATION_ID, buildNotification());
        } catch (Throwable e) {
            prefs.edit().putString("service_last_error", "foreground: " + e.getClass().getSimpleName()).apply();
        }
        registerCommands();
        prefs.edit()
                .putBoolean("service_connected", true)
                .putString("service_boot_status", "OVERLAY SERVICE OK • SIN ACCESIBILIDAD")
                .putLong("overlay_service_heartbeat", System.currentTimeMillis())
                .apply();
        handler.post(foregroundMonitor);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        prefs.edit().putLong("overlay_service_heartbeat", System.currentTimeMillis()).apply();
        return START_STICKY;
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                NotificationChannel ch = new NotificationChannel(
                        CHANNEL_ID, "CODM Crosshair", NotificationManager.IMPORTANCE_LOW);
                ch.setDescription("Mantiene activo el overlay del crosshair");
                nm.createNotificationChannel(ch);
            }
        }
    }

    private Notification buildNotification() {
        Notification.Builder b = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return b.setContentTitle("CODM Crosshair")
                .setContentText("Overlay automático activo")
                .setSmallIcon(R.drawable.ic_crosshair)
                .setOngoing(true)
                .build();
    }

    private void registerCommands() {
        commandReceiver = new BroadcastReceiver() {
            @Override public void onReceive(Context context, Intent intent) {
                if (intent == null || intent.getAction() == null) return;
                try {
                    String action = intent.getAction();
                    if (ACTION_TEST.equals(action)) {
                        startTestMode();
                    } else if (ACTION_UPDATE.equals(action)) {
                        if (showing) showOrUpdate();
                    } else if (ACTION_HIDE.equals(action)) {
                        testMode = false;
                        hideNow(false);
                    } else if (ACTION_ENABLE.equals(action)) {
                        String active = getForegroundPackage();
                        if (isCodm(active)) {
                            gameSessionActive = true;
                            currentCodmPackage = active;
                        }
                        if (gameSessionActive && prefs.getBoolean("auto_enabled", true)) showOrUpdate();
                    } else if (ACTION_PANEL_MOVE.equals(action)) {
                        prefs.edit().putBoolean("stats_locked", false).apply();
                        if (showing) {
                            createStatsOverlayIfEnabled();
                            applyStatsInteractionMode();
                        }
                    } else if (ACTION_PANEL_LOCK.equals(action)) {
                        lockStatsPanel();
                    }
                } catch (Throwable e) {
                    prefs.edit().putString("service_last_error", "command: " + e.getClass().getSimpleName()).apply();
                }
            }
        };
        IntentFilter filter = new IntentFilter();
        filter.addAction(ACTION_TEST);
        filter.addAction(ACTION_UPDATE);
        filter.addAction(ACTION_HIDE);
        filter.addAction(ACTION_ENABLE);
        filter.addAction(ACTION_PANEL_MOVE);
        filter.addAction(ACTION_PANEL_LOCK);
        try {
            if (Build.VERSION.SDK_INT >= 33) registerReceiver(commandReceiver, filter, RECEIVER_NOT_EXPORTED);
            else registerReceiver(commandReceiver, filter);
        } catch (Throwable e) {
            prefs.edit().putString("service_last_error", "receiver: " + e.getClass().getSimpleName()).apply();
        }
    }

    private void monitorForegroundApp() {
        try {
            prefs.edit().putLong("overlay_service_heartbeat", System.currentTimeMillis()).apply();

            if (!Settings.canDrawOverlays(this)) {
                prefs.edit().putString("detector_status", "FALTA SUPERPOSICIÓN").apply();
                hideNow(false);
                return;
            }
            if (!hasUsageAccess()) {
                prefs.edit().putString("detector_status", "FALTA ACCESO DE USO").apply();
                hideNow(false);
                return;
            }

            String pkg = getForegroundPackage();
            if (pkg != null && !pkg.isEmpty()) {
                prefs.edit().putString("last_package", pkg).apply();
            }

            if (isCodm(pkg)) {
                currentCodmPackage = pkg;
                gameSessionActive = true;
                prefs.edit()
                        .putString("last_codm_package", pkg)
                        .putString("detector_status", "CODM DETECTADO • UsageStats")
                        .apply();
                if (prefs.getBoolean("auto_enabled", true)) {
                    testMode = false;
                    showOrUpdate();
                } else {
                    hideNow(false);
                }
            } else if (!testMode && !isTransientOverlay(pkg)) {
                gameSessionActive = false;
                hideNow(false);
            }
        } catch (Throwable e) {
            prefs.edit().putString("service_last_error", "monitor: " + e.getClass().getSimpleName()).apply();
        } finally {
            handler.removeCallbacks(foregroundMonitor);
            handler.postDelayed(foregroundMonitor, 650L);
        }
    }

    private boolean hasUsageAccess() {
        try {
            AppOpsManager appOps = (AppOpsManager) getSystemService(APP_OPS_SERVICE);
            if (appOps == null) return false;
            int mode = appOps.checkOpNoThrow(
                    AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), getPackageName());
            return mode == AppOpsManager.MODE_ALLOWED;
        } catch (Throwable e) {
            return false;
        }
    }

    private String getForegroundPackage() {
        try {
            UsageStatsManager usm = (UsageStatsManager) getSystemService(USAGE_STATS_SERVICE);
            if (usm == null) return "";
            long now = System.currentTimeMillis();
            UsageEvents events = usm.queryEvents(now - 6000L, now);
            UsageEvents.Event event = new UsageEvents.Event();
            String latest = "";
            long latestTime = 0L;
            while (events != null && events.hasNextEvent()) {
                events.getNextEvent(event);
                int type = event.getEventType();
                boolean foreground = type == UsageEvents.Event.MOVE_TO_FOREGROUND;
                if (Build.VERSION.SDK_INT >= 29) {
                    foreground |= type == UsageEvents.Event.ACTIVITY_RESUMED;
                }
                if (foreground && event.getTimeStamp() >= latestTime) {
                    latestTime = event.getTimeStamp();
                    latest = event.getPackageName();
                }
            }
            if (!latest.isEmpty()) return latest;

            List<UsageStats> stats = usm.queryUsageStats(
                    UsageStatsManager.INTERVAL_DAILY, now - 15000L, now);
            if (stats != null) {
                UsageStats best = null;
                for (UsageStats s : stats) {
                    if (best == null || s.getLastTimeUsed() > best.getLastTimeUsed()) best = s;
                }
                if (best != null) return best.getPackageName();
            }
        } catch (Throwable ignored) { }
        return "";
    }

    private boolean isCodm(String pkg) {
        if (pkg == null) return false;
        String p = pkg.toLowerCase(Locale.ROOT);
        return GLOBAL_PACKAGE.equals(pkg)
                || GARENA_PACKAGE.equals(pkg)
                || p.contains("callofduty")
                || p.contains("codm");
    }

    private boolean isTransientOverlay(String pkg) {
        if (pkg == null) return true;
        String p = pkg.toLowerCase(Locale.ROOT);
        return p.isEmpty()
                || p.equals("com.android.systemui")
                || p.contains("gamebooster")
                || p.contains("gamecenter")
                || p.equals("com.miui.securitycenter")
                || p.equals("com.xiaomi.joyose")
                || p.contains("floating")
                || p.contains("sidebar");
    }

    private void showOrUpdate() {
        if (windowManager == null || !Settings.canDrawOverlays(this)) return;
        float scale = prefs.getFloat("scale", 0.40f);
        int xDp = prefs.getInt("x", 0);
        int yDp = prefs.getInt("y", 0);
        float density = getResources().getDisplayMetrics().density;
        int totalSizePx = Math.max(1, Math.round(74f * scale * density));

        if (!showing) {
            crosshairView = new CrosshairView(this);
            crosshairView.setScaleFactor(scale);
            crosshairView.setCrosshairColor(prefs.getInt("crosshair_color", CrosshairView.GREEN));
            params = new WindowManager.LayoutParams(
                    totalSizePx, totalSizePx,
                    WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                            | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                            | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                            | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                    PixelFormat.TRANSLUCENT);
            params.gravity = Gravity.CENTER;
            params.x = Math.round(xDp * density);
            params.y = Math.round(yDp * density);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                params.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS;
            }
            try {
                windowManager.addView(crosshairView, params);
                showing = true;
                prefs.edit().putString("overlay_status", "VISIBLE • APPLICATION_OVERLAY").apply();
                createStatsOverlayIfEnabled();
                startStatsSampling();
            } catch (Throwable e) {
                showing = false;
                prefs.edit().putString("overlay_status", "ERROR " + e.getClass().getSimpleName()).apply();
            }
        } else {
            crosshairView.setScaleFactor(scale);
            crosshairView.setCrosshairColor(prefs.getInt("crosshair_color", CrosshairView.GREEN));
            params.width = totalSizePx;
            params.height = totalSizePx;
            params.x = Math.round(xDp * density);
            params.y = Math.round(yDp * density);
            try { windowManager.updateViewLayout(crosshairView, params); } catch (Throwable ignored) { }

            if (prefs.getBoolean("stats_enabled", true)) {
                createStatsOverlayIfEnabled();
                updateStatsAppearance();
                applyStatsInteractionMode();
                startStatsSampling();
            } else {
                removeStatsOverlay();
                stopStatsSampling();
            }
        }
    }

    private void createStatsOverlayIfEnabled() {
        if (!prefs.getBoolean("stats_enabled", true) || statsView != null || windowManager == null) return;
        if (!Settings.canDrawOverlays(this)) return;
        float density = getResources().getDisplayMetrics().density;
        statsView = new TextView(this);
        statsView.setText("—%\n— °C\n— FPS");
        statsView.setTextColor(prefs.getInt("crosshair_color", CrosshairView.GREEN));
        statsView.setTextSize(12f * prefs.getFloat("stats_scale", 1.00f));

        int screenWidth = getResources().getDisplayMetrics().widthPixels;
        int defaultXDp = Math.max(8, Math.round(screenWidth / density) - 132);
        int xDp = prefs.getInt("stats_x_dp", defaultXDp);
        int yDp = prefs.getInt("stats_y_dp", 58);

        statsParams = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        statsParams.gravity = Gravity.TOP | Gravity.START;
        statsParams.x = Math.max(0, Math.round(xDp * density));
        statsParams.y = Math.max(0, Math.round(yDp * density));
        try {
            windowManager.addView(statsView, statsParams);
            updateStatsAppearance();
            applyStatsInteractionMode();
        } catch (Throwable e) {
            statsView = null;
            statsParams = null;
            prefs.edit().putString("service_last_error", "stats-overlay: " + e.getClass().getSimpleName()).apply();
        }
    }

    private void updateStatsAppearance() {
        if (statsView == null) return;
        float panelScale = Math.max(0.50f, Math.min(2.00f, prefs.getFloat("stats_scale", 1.00f)));
        float density = getResources().getDisplayMetrics().density;
        statsView.setTextSize(12f * panelScale);
        statsView.setTextColor(prefs.getInt("crosshair_color", CrosshairView.GREEN));
        statsView.setPadding(
                Math.round(8 * density * panelScale),
                Math.round(4 * density * panelScale),
                Math.round(8 * density * panelScale),
                Math.round(4 * density * panelScale));
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.argb(135, 0, 0, 0));
        bg.setCornerRadius(7f * density);
        if (!prefs.getBoolean("stats_locked", true)) {
            bg.setStroke(Math.max(1, Math.round(density)),
                    prefs.getInt("crosshair_color", CrosshairView.GREEN));
        }
        statsView.setBackground(bg);
    }

    private void applyStatsInteractionMode() {
        if (statsView == null || statsParams == null || windowManager == null) return;
        boolean locked = prefs.getBoolean("stats_locked", true);
        statsParams.flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | (locked ? WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE : 0);
        statsView.setOnTouchListener(locked ? null : this::handleStatsTouch);
        updateStatsAppearance();
        try { windowManager.updateViewLayout(statsView, statsParams); } catch (Throwable ignored) { }
    }

    private boolean handleStatsTouch(View v, MotionEvent event) {
        if (statsParams == null || windowManager == null) return false;
        float density = getResources().getDisplayMetrics().density;
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                panelDownX = event.getRawX();
                panelDownY = event.getRawY();
                panelDragOffsetX = statsParams.x - event.getRawX();
                panelDragOffsetY = statsParams.y - event.getRawY();
                panelDragged = false;
                return true;
            case MotionEvent.ACTION_MOVE:
                if (Math.abs(event.getRawX() - panelDownX) > density * 4
                        || Math.abs(event.getRawY() - panelDownY) > density * 4) panelDragged = true;
                statsParams.x = Math.max(0, Math.round(event.getRawX() + panelDragOffsetX));
                statsParams.y = Math.max(0, Math.round(event.getRawY() + panelDragOffsetY));
                try { windowManager.updateViewLayout(statsView, statsParams); } catch (Throwable ignored) { }
                return true;
            case MotionEvent.ACTION_UP:
                prefs.edit()
                        .putInt("stats_x_dp", Math.round(statsParams.x / density))
                        .putInt("stats_y_dp", Math.round(statsParams.y / density))
                        .apply();
                if (!panelDragged) lockStatsPanel();
                return true;
            default:
                return false;
        }
    }

    private void lockStatsPanel() {
        prefs.edit().putBoolean("stats_locked", true).apply();
        applyStatsInteractionMode();
    }

    private synchronized ShizukuFpsClient ensureFpsClient() {
        if (fpsClient != null) return fpsClient;
        try {
            fpsClient = new ShizukuFpsClient(this, ready -> {
                try { prefs.edit().putBoolean("shizuku_fps_connected", ready).apply(); }
                catch (Throwable ignored) { }
            });
            return fpsClient;
        } catch (Throwable e) {
            fpsClient = null;
            prefs.edit().putString("service_last_error", "fps-init: " + e.getClass().getSimpleName()).apply();
            return null;
        }
    }

    private synchronized void startStatsSampling() {
        if (statsExecutor != null && !statsExecutor.isShutdown()) return;
        statsExecutor = Executors.newSingleThreadScheduledExecutor();
        statsExecutor.scheduleWithFixedDelay(() -> {
            try { sampleStats(); }
            catch (Throwable e) {
                prefs.edit().putString("service_last_error", "sampler: " + e.getClass().getSimpleName()).apply();
            }
        }, 350, 2000, TimeUnit.MILLISECONDS);
    }

    private void sampleStats() {
        if (!showing || statsView == null) return;

        int battery = -1;
        try {
            BatteryManager bm = (BatteryManager) getSystemService(BATTERY_SERVICE);
            if (bm != null) battery = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY);
        } catch (Throwable ignored) { }

        int temp10 = -1;
        try {
            Intent bi = registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
            if (bi != null) temp10 = bi.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, -1);
        } catch (Throwable ignored) { }

        float fps = -1f;
        if (prefs.getBoolean("fps_enabled", true)) {
            try {
                ShizukuFpsClient client = ensureFpsClient();
                if (client != null) {
                    if (!client.isConnected() && client.isShizukuReady()) client.connect();
                    if (client.isConnected()) fps = stabilizeFps(client.readFps(currentCodmPackage));
                }
            } catch (Throwable e) {
                fps = -1f;
                prefs.edit().putString("service_last_error", "fps: " + e.getClass().getSimpleName()).apply();
            }
        }

        final int b = battery;
        final int t = temp10;
        final float f = fps;
        prefs.edit()
                .putInt("last_battery", b)
                .putInt("last_battery_temp_tenths", t)
                .putInt("last_fps", f >= 0f ? Math.round(f) : -1)
                .putFloat("last_fps_exact", f)
                .putString("fps_status", fpsClient != null ? fpsClient.getLastStatus() : "—")
                .putString("fps_layer", fpsClient != null ? fpsClient.getLastLayer() : "—")
                .apply();

        handler.post(() -> {
            if (statsView == null) return;
            StringBuilder s = new StringBuilder();
            boolean first = true;
            if (prefs.getBoolean("battery_enabled", true)) {
                s.append(b >= 0 ? b + "%" : "—%");
                first = false;
            }
            if (prefs.getBoolean("temperature_enabled", true)) {
                if (!first) s.append("\n");
                s.append(t >= 0 ? String.format(Locale.US, "%.1f °C", t / 10f) : "— °C");
                first = false;
            }
            if (prefs.getBoolean("fps_enabled", true)) {
                if (!first) s.append("\n");
                if (f >= 0f) s.append(String.format(Locale.US, "%.1f FPS", f));
                else s.append("— FPS");
            }
            statsView.setText(s.toString());
        });
    }

    private float stabilizeFps(float rawFps) {
        if (rawFps < 1f) return -1f;
        return Math.round(Math.min(rawFps, 120.0f) * 10f) / 10f;
    }

    private synchronized void stopStatsSampling() {
        if (statsExecutor != null) {
            statsExecutor.shutdownNow();
            statsExecutor = null;
        }
        try {
            if (fpsClient != null) fpsClient.disconnect();
        } catch (Throwable ignored) { }
    }

    private void startTestMode() {
        testMode = true;
        gameSessionActive = true;
        showOrUpdate();
        handler.postDelayed(() -> {
            if (testMode) {
                testMode = false;
                gameSessionActive = false;
                hideNow(false);
            }
        }, 8000L);
    }

    private void hideNow(boolean destroyFps) {
        if (windowManager != null) {
            if (crosshairView != null) {
                try { windowManager.removeView(crosshairView); } catch (Throwable ignored) { }
            }
            removeStatsOverlay();
        }
        crosshairView = null;
        params = null;
        showing = false;
        stopStatsSampling();
        prefs.edit().putString("overlay_status", "OCULTO").apply();
    }

    private void removeStatsOverlay() {
        if (statsView != null && windowManager != null) {
            try { windowManager.removeView(statsView); } catch (Throwable ignored) { }
        }
        statsView = null;
        statsParams = null;
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        hideNow(true);
        try { if (commandReceiver != null) unregisterReceiver(commandReceiver); } catch (Throwable ignored) { }
        prefs.edit().putBoolean("service_connected", false).apply();
        try { stopForeground(STOP_FOREGROUND_REMOVE); } catch (Throwable ignored) { }
        super.onDestroy();
    }
}
''')

# MainActivity: sustituimos Accesibilidad por permisos de overlay + uso.
main = root / 'app/src/main/java/com/codm/crosshair/MainActivity.java'
t = main.read_text()

# imports
if 'import android.app.AppOpsManager;' not in t:
    t = t.replace('import android.app.Activity;\n', 'import android.app.Activity;\nimport android.app.AppOpsManager;\n')
if 'import android.net.Uri;' not in t:
    t = t.replace('import android.graphics.drawable.Icon;\n', 'import android.graphics.drawable.Icon;\nimport android.net.Uri;\n')
if 'import android.os.Process;' not in t:
    t = t.replace('import android.os.Bundle;\n', 'import android.os.Bundle;\nimport android.os.Process;\n')

t = t.replace('CODM CROSSHAIR AUTO • v21', 'CODM CROSSHAIR AUTO • v22')
t = t.replace(
    'Crosshair ECO + panel arrastrable/bloqueable y lector FPS reforzado con SurfaceFlinger TimeStats + Shizuku. Bloqueado, el panel no intercepta ningún toque del juego.',
    'Crosshair ECO sin Accesibilidad: usa Superposición + Acceso de uso para detectar COD Mobile. Shizuku se usa únicamente para FPS. El panel bloqueado no intercepta toques.'
)

old_buttons = '''        Button access = new Button(this);
        access.setText("ACTIVAR / ABRIR ACCESIBILIDAD");
        root.addView(access);

        Button test = new Button(this);
'''
new_buttons = '''        Button access = new Button(this);
        access.setText("1. PERMITIR MOSTRAR SOBRE OTRAS APPS");
        root.addView(access);

        Button usage = new Button(this);
        usage.setText("2. PERMITIR ACCESO DE USO");
        root.addView(usage);

        Button startService = new Button(this);
        startService.setText("3. INICIAR / REINICIAR SERVICIO");
        root.addView(startService);

        Button test = new Button(this);
'''
if old_buttons not in t:
    raise SystemExit('No se encontró botón Accesibilidad en MainActivity')
t = t.replace(old_buttons, new_buttons, 1)

old_listeners = '''        access.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        test.setOnClickListener(v -> {
            savePrefs();
            if (!isAccessibilityServiceEnabled()) {
                status.setText("Primero activa CODM Crosshair Automático en Accesibilidad");
                status.setTextColor(Color.rgb(255, 80, 80));
                return;
            }
            sendBroadcast(new Intent(CodmAccessibilityService.ACTION_TEST).setPackage(getPackageName()));
            status.setText("PRUEBA: crosshair y datos durante 8 segundos");
            status.setTextColor(CrosshairView.GREEN);
        });
'''
new_listeners = '''        access.setOnClickListener(v -> {
            try {
                startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + getPackageName())));
            } catch (Throwable e) {
                startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION));
            }
        });
        usage.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)));
        startService.setOnClickListener(v -> {
            startOverlayService();
            updateStatus();
        });
        test.setOnClickListener(v -> {
            savePrefs();
            if (!Settings.canDrawOverlays(this)) {
                status.setText("Falta permiso: Mostrar sobre otras apps");
                status.setTextColor(Color.rgb(255, 80, 80));
                return;
            }
            if (!hasUsageAccess()) {
                status.setText("Falta permiso: Acceso de uso");
                status.setTextColor(Color.rgb(255, 80, 80));
                return;
            }
            startOverlayService();
            sendBroadcast(new Intent(GameOverlayService.ACTION_TEST).setPackage(getPackageName()));
            status.setText("PRUEBA: crosshair y datos durante 8 segundos");
            status.setTextColor(CrosshairView.GREEN);
        });
'''
if old_listeners not in t:
    raise SystemExit('No se encontraron listeners Accesibilidad/test')
t = t.replace(old_listeners, new_listeners, 1)

# Broadcasts de UI al nuevo servicio.
t = t.replace('CodmAccessibilityService.ACTION_UPDATE', 'GameOverlayService.ACTION_UPDATE')
t = t.replace('CodmAccessibilityService.ACTION_PANEL_MOVE', 'GameOverlayService.ACTION_PANEL_MOVE')

# onResume arranca servicio si ya tiene permisos.
old_resume = '''        updateStatus();
        updateShizukuStatus();
'''
new_resume = '''        if (Settings.canDrawOverlays(this) && hasUsageAccess()) startOverlayService();
        updateStatus();
        updateShizukuStatus();
'''
# solo primera coincidencia de onResume; puede haber otras, el último contexto es suficiente.
idx = t.rfind(old_resume)
if idx < 0:
    raise SystemExit('No se encontró onResume status')
t = t[:idx] + new_resume + t[idx + len(old_resume):]

# Sustituimos updateStatus por estado real de los dos permisos y heartbeat.
start = t.find('    private void updateStatus() {')
end = t.find('    private boolean isAccessibilityServiceEnabled()', start)
if start < 0 or end < 0:
    raise SystemExit('No se encontró updateStatus/isAccessibilityServiceEnabled')
new_status = '''    private void updateStatus() {
        boolean overlay = Settings.canDrawOverlays(this);
        boolean usage = hasUsageAccess();
        long heartbeat = prefs.getLong("overlay_service_heartbeat", 0L);
        boolean alive = System.currentTimeMillis() - heartbeat < 5000L;

        if (overlay && usage) {
            status.setText(alive
                    ? "Servicio: ACTIVO • sin Accesibilidad"
                    : "Permisos OK • toca INICIAR SERVICIO");
            status.setTextColor(CrosshairView.GREEN);
        } else {
            status.setText("Falta: "
                    + (!overlay ? "SUPERPOSICIÓN " : "")
                    + (!usage ? "ACCESO DE USO" : ""));
            status.setTextColor(Color.rgb(255, 80, 80));
        }
    }

    private boolean hasUsageAccess() {
        try {
            AppOpsManager appOps = (AppOpsManager) getSystemService(APP_OPS_SERVICE);
            if (appOps == null) return false;
            int mode = appOps.checkOpNoThrow(
                    AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), getPackageName());
            return mode == AppOpsManager.MODE_ALLOWED;
        } catch (Throwable e) {
            return false;
        }
    }

    private void startOverlayService() {
        try {
            Intent i = new Intent(this, GameOverlayService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(i);
            else startService(i);
        } catch (Throwable e) {
            if (prefs != null) prefs.edit()
                    .putString("service_last_error", "start: " + e.getClass().getSimpleName())
                    .apply();
        }
    }

'''
t = t[:start] + new_status + t[end:]

# Ya no usamos el verificador de Accessibility; lo dejamos fuera para evitar confusión.
start = t.find('    private boolean isAccessibilityServiceEnabled()')
if start >= 0:
    end = t.find('    private abstract static class SimpleSeek', start)
    if end < 0:
        raise SystemExit('No se encontró fin isAccessibilityServiceEnabled')
    t = t[:start] + t[end:]

# Diagnóstico añade detector/servicio.
diag_old = 'String fpsLayer = prefs.getString("fps_layer", "—");'
diag_new = '''String fpsLayer = prefs.getString("fps_layer", "—");
            String detector = prefs.getString("detector_status", "—");
            String serviceError = prefs.getString("service_last_error", "—");'''
if diag_old in t:
    t = t.replace(diag_old, diag_new, 1)

diag_tail = '"\nEstado FPS: " + fpsStatus + "\nCapa FPS: " + fpsLayer);'
diag_tail_new = '"\nEstado FPS: " + fpsStatus + "\nCapa FPS: " + fpsLayer + "\nDetector: " + detector + "\nError servicio: " + serviceError);'
if diag_tail in t:
    t = t.replace(diag_tail, diag_tail_new, 1)

main.write_text(t)

# Tiles: garantizan que el FGS esté vivo antes de mandar comandos.
for name in ['CrosshairTileService.java', 'PanelMoveTileService.java']:
    p = root / 'app/src/main/java/com/codm/crosshair' / name
    x = p.read_text()
    marker = '        SharedPreferences prefs = getSharedPreferences("crosshair", MODE_PRIVATE);'
    if marker in x:
        inject = '''        try {
            Intent svc = new Intent(this, GameOverlayService.class);
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) startForegroundService(svc);
            else startService(svc);
        } catch (Throwable ignored) { }
'''
        x = x.replace(marker, inject + marker, 1)
    x = x.replace('CodmAccessibilityService.ACTION_ENABLE', 'GameOverlayService.ACTION_ENABLE')
    x = x.replace('CodmAccessibilityService.ACTION_HIDE', 'GameOverlayService.ACTION_HIDE')
    x = x.replace('CodmAccessibilityService.ACTION_PANEL_LOCK', 'GameOverlayService.ACTION_PANEL_LOCK')
    x = x.replace('CodmAccessibilityService.ACTION_PANEL_MOVE', 'GameOverlayService.ACTION_PANEL_MOVE')
    p.write_text(x)

# Validaciones
assert 'versionCode 22' in gradle.read_text()
assert 'GameOverlayService' in manifest.read_text()
assert 'CodmAccessibilityService' not in manifest.read_text()
assert 'TYPE_APPLICATION_OVERLAY' in game_service.read_text()
assert 'UsageStatsManager' in game_service.read_text()
assert 'ACTION_MANAGE_OVERLAY_PERMISSION' in main.read_text()
assert 'ACTION_USAGE_ACCESS_SETTINGS' in main.read_text()
