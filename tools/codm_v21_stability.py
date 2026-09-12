from pathlib import Path
import runpy

# Primero aplica exactamente la mejora FPS BLAST de v20.
runpy.run_path('tools/codm_v20_transform.py', run_name='__main__')

root = Path('CODMCrosshair_Auto')
gradle = root / 'app/build.gradle'
s = gradle.read_text().replace('versionCode 20', 'versionCode 21').replace("versionName '20.0'", "versionName '21.0'")
gradle.write_text(s)

service = root / 'app/src/main/java/com/codm/crosshair/CodmAccessibilityService.java'
t = service.read_text()

# v21: Shizuku/FPS NO se inicializa durante onServiceConnected().
# De esta manera un fallo del lector FPS jamás puede hacer que Android apague
# el servicio de Accesibilidad al activarlo.
old_client = '''        fpsClient = new ShizukuFpsClient(this, ready -> {
            if (prefs != null) prefs.edit().putBoolean("shizuku_fps_connected", ready).apply();
        });
'''
new_client = '''        // v21: cliente FPS lazy. Accesibilidad debe poder arrancar sin Shizuku.
        fpsClient = null;
        prefs.edit()
                .putBoolean("service_connected", true)
                .putString("service_boot_status", "ACCESIBILIDAD OK • FPS AISLADO")
                .apply();
'''
if old_client not in t:
    raise SystemExit('No se encontró inicialización fpsClient')
t = t.replace(old_client, new_client, 1)

# La configuración ya está declarada en accessibility_service_config.xml.
# Evitamos reconfigurar el servicio en runtime porque algunas versiones de
# HyperOS pueden lanzar una excepción aquí y desactivar el servicio.
old_info = '''        AccessibilityServiceInfo info = getServiceInfo();
        if (info != null) {
            info.eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
                    | AccessibilityEvent.TYPE_WINDOWS_CHANGED;
            info.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
            info.notificationTimeout = 180;
            setServiceInfo(info);
        }
'''
new_info = '''        // La configuración de eventos/ventanas se toma del XML del servicio.
        // No llamamos setServiceInfo() durante el arranque para máxima compatibilidad HyperOS.
'''
if old_info not in t:
    raise SystemExit('No se encontró bloque setServiceInfo')
t = t.replace(old_info, new_info, 1)

# El registro del receiver tampoco puede tumbar Accesibilidad.
old_register = '''        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(commandReceiver, filter, RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(commandReceiver, filter);
        }

        prefs.edit().putBoolean("service_connected", true).apply();
'''
new_register = '''        try {
            if (Build.VERSION.SDK_INT >= 33) {
                registerReceiver(commandReceiver, filter, RECEIVER_NOT_EXPORTED);
            } else {
                registerReceiver(commandReceiver, filter);
            }
            prefs.edit().putBoolean("command_receiver_ok", true).apply();
        } catch (Throwable e) {
            prefs.edit()
                    .putBoolean("command_receiver_ok", false)
                    .putString("service_last_error", "receiver: " + e.getClass().getSimpleName())
                    .apply();
        }

        prefs.edit().putBoolean("service_connected", true).apply();
'''
if old_register not in t:
    raise SystemExit('No se encontró registro receiver')
t = t.replace(old_register, new_register, 1)

# Blindaje de todos los eventos de accesibilidad. Un error del overlay/FPS no
# debe propagarse al framework de Android.
old_event = '''    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
'''
new_event = '''    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        try {
            handleAccessibilityEventSafe(event);
        } catch (Throwable e) {
            try {
                if (prefs == null) prefs = getSharedPreferences("crosshair", MODE_PRIVATE);
                prefs.edit().putString("service_last_error", "event: " + e.getClass().getSimpleName()).apply();
            } catch (Throwable ignored) { }
        }
    }

    private void handleAccessibilityEventSafe(AccessibilityEvent event) {
'''
if old_event not in t:
    raise SystemExit('No se encontró onAccessibilityEvent')
t = t.replace(old_event, new_event, 1)

# Cliente Shizuku lazy y tolerante a fallos. Se crea únicamente cuando el panel
# FPS realmente lo necesita, ya con CODM abierto.
anchor = '    private synchronized void startStatsSampling() {'
lazy = '''    private synchronized ShizukuFpsClient ensureFpsClient() {
        if (fpsClient != null) return fpsClient;
        try {
            fpsClient = new ShizukuFpsClient(this, ready -> {
                try {
                    if (prefs != null) prefs.edit().putBoolean("shizuku_fps_connected", ready).apply();
                } catch (Throwable ignored) { }
            });
            if (prefs != null) prefs.edit().putString("fps_client_status", "CREADO").apply();
            return fpsClient;
        } catch (Throwable e) {
            fpsClient = null;
            try {
                if (prefs != null) prefs.edit()
                        .putString("fps_client_status", "ERROR " + e.getClass().getSimpleName())
                        .putString("service_last_error", "fps-init: " + e.getClass().getSimpleName())
                        .apply();
            } catch (Throwable ignored) { }
            return null;
        }
    }

'''
if anchor not in t:
    raise SystemExit('No se encontró startStatsSampling')
t = t.replace(anchor, lazy + anchor, 1)

old_start = '''        if (prefs.getBoolean("fps_enabled", true) && fpsClient != null && fpsClient.isShizukuReady()) {
            fpsClient.connect();
        }
'''
new_start = '''        if (prefs.getBoolean("fps_enabled", true)) {
            try {
                ShizukuFpsClient client = ensureFpsClient();
                if (client != null && client.isShizukuReady()) client.connect();
            } catch (Throwable e) {
                try { prefs.edit().putString("service_last_error", "fps-start: " + e.getClass().getSimpleName()).apply(); } catch (Throwable ignored) { }
            }
        }
'''
if old_start not in t:
    raise SystemExit('No se encontró arranque FPS')
t = t.replace(old_start, new_start, 1)

old_sample = '''        boolean fpsEnabled = prefs.getBoolean("fps_enabled", true);
        if (fpsEnabled && fpsClient != null) {
            if (!fpsClient.isConnected() && fpsClient.isShizukuReady()) {
                fpsClient.connect();
            }
            if (fpsClient.isConnected()) {
                fps = stabilizeFps(fpsClient.readFps(currentCodmPackage));
            }
        }
'''
new_sample = '''        boolean fpsEnabled = prefs.getBoolean("fps_enabled", true);
        if (fpsEnabled) {
            try {
                ShizukuFpsClient client = ensureFpsClient();
                if (client != null) {
                    if (!client.isConnected() && client.isShizukuReady()) client.connect();
                    if (client.isConnected()) fps = stabilizeFps(client.readFps(currentCodmPackage));
                }
            } catch (Throwable e) {
                fps = -1f;
                try { prefs.edit().putString("service_last_error", "fps-sample: " + e.getClass().getSimpleName()).apply(); } catch (Throwable ignored) { }
            }
        }
'''
if old_sample not in t:
    raise SystemExit('No se encontró lectura FPS')
t = t.replace(old_sample, new_sample, 1)

# El propio Runnable del sampler queda blindado contra cualquier Throwable.
old_schedule = '        statsExecutor.scheduleWithFixedDelay(this::sampleStats, 200, 2000, TimeUnit.MILLISECONDS);'
new_schedule = '''        statsExecutor.scheduleWithFixedDelay(() -> {
            try {
                sampleStats();
            } catch (Throwable e) {
                try {
                    if (prefs != null) prefs.edit().putString("service_last_error", "sampler: " + e.getClass().getSimpleName()).apply();
                } catch (Throwable ignored) { }
            }
        }, 350, 2000, TimeUnit.MILLISECONDS);'''
if old_schedule not in t:
    raise SystemExit('No se encontró schedule sampler')
t = t.replace(old_schedule, new_schedule, 1)

# onInterrupt nunca debe lanzar una excepción al framework.
t = t.replace('    @Override public void onInterrupt() { hideNow(true); }',
              '    @Override public void onInterrupt() { try { hideNow(true); } catch (Throwable ignored) { } }', 1)

service.write_text(t)

main = root / 'app/src/main/java/com/codm/crosshair/MainActivity.java'
mt = main.read_text().replace('CODM CROSSHAIR AUTO • v20', 'CODM CROSSHAIR AUTO • v21')
main.write_text(mt)

assert 'versionCode 21' in gradle.read_text()
assert 'FPS EXACTO • SurfaceView/BLAST CODM' in (root / 'app/src/main/java/com/codm/crosshair/ShizukuFpsClient.java').read_text()
assert 'ACCESIBILIDAD OK • FPS AISLADO' in service.read_text()
assert 'ensureFpsClient()' in service.read_text()
assert 'handleAccessibilityEventSafe' in service.read_text()
