from pathlib import Path
import re

root = Path('CODMCrosshair_Auto')

gradle = root / 'app/build.gradle'
s = gradle.read_text().replace('versionCode 16', 'versionCode 20').replace("versionName '16.0'", "versionName '20.0'")
gradle.write_text(s)

manifest = root / 'app/src/main/AndroidManifest.xml'
s = manifest.read_text()
def repl_app(m):
    attrs = m.group(1)
    attrs = re.sub(r'\s+android:(?:icon|roundIcon)="[^"]*"', '', attrs)
    return '<application' + attrs + '\n        android:icon="@drawable/ic_launcher_crosshair"\n        android:roundIcon="@drawable/ic_launcher_crosshair">'
s, n = re.subn(r'<application\b([^>]*)>', repl_app, s, count=1, flags=re.S)
if n != 1:
    raise SystemExit('No se encontró <application>')
manifest.write_text(s)

client = root / 'app/src/main/java/com/codm/crosshair/ShizukuFpsClient.java'
c = client.read_text()
c = c.replace('.tag("codm_fps_shell_v14")\n                    .version(14);', '.tag("codm_fps_shell_v20")\n                    .version(20);')

field_anchor = '    private long lastPageFlipAtMs = 0L;\n'
extra_fields = '''    private long lastPageFlipAtMs = 0L;
    private long exactLayerSelectedAtMs = 0L;
    private int exactLayerFailures = 0;
    private String exactFocusedComponent = "";
'''
if field_anchor not in c:
    raise SystemExit('No se encontró anchor campos FPS')
c = c.replace(field_anchor, extra_fields, 1)

reset_anchor = '        lastPageFlipAtMs = 0L;\n'
reset_extra = '''        lastPageFlipAtMs = 0L;
        exactLayerSelectedAtMs = 0L;
        exactLayerFailures = 0;
        exactFocusedComponent = "";
'''
idx = c.find(reset_anchor, c.find('public synchronized void disconnect()'))
if idx < 0:
    raise SystemExit('No se encontró reset disconnect')
c = c[:idx] + reset_extra + c[idx + len(reset_anchor):]

read_start = c.find('    public int readFps(String packageName) {')
read_end = c.find('    private int readPageFlipFps() {', read_start)
if read_start < 0 or read_end < 0:
    raise SystemExit('No se encontró readFps')

new_read = r'''    public float readFps(String packageName) {
        IFpsShell local;
        synchronized (this) { local = shell; }
        if (local == null) {
            lastStatus = isShizukuReady() ? "Conectando lector FPS…" : "Shizuku inactivo o sin permiso";
            return -1f;
        }

        String safePkg = packageName == null ? "" : packageName.replaceAll("[^A-Za-z0-9._]", "");
        if (safePkg.isEmpty()) {
            lastStatus = "Paquete de CODM no detectado";
            return -1f;
        }

        // v20: fuente principal = timestamps de presentación de la SurfaceView/BLAST
        // que pertenece a COD Mobile. No usamos page-flips globales como fuente principal.
        String exactLayer;
        long selectedAt;
        synchronized (this) {
            if (!safePkg.equals(cachedPackage)) {
                cachedPackage = safePkg;
                cachedLayer = "";
                exactFocusedComponent = "";
                exactLayerFailures = 0;
                exactLayerSelectedAtMs = 0L;
            }
            exactLayer = cachedLayer;
            selectedAt = exactLayerSelectedAtMs;
        }

        if (!exactLayer.isEmpty()) {
            float fps = readLayerFpsExact(exactLayer);
            if (fps > 0f) {
                synchronized (this) { exactLayerFailures = 0; }
                lastStatus = "FPS EXACTO • SurfaceView/BLAST CODM" + shellSuffix();
                lastLayer = shortLayer(exactLayer);
                return fps;
            }
            synchronized (this) {
                exactLayerFailures++;
                if (exactLayerFailures >= 3) {
                    cachedLayer = "";
                    exactLayer = "";
                    exactLayerSelectedAtMs = 0L;
                }
            }
            if (!exactLayer.isEmpty() && System.currentTimeMillis() - selectedAt < 2500L) {
                lastStatus = "FPS exacto • llenando buffer BLAST" + shellSuffix();
                lastLayer = shortLayer(exactLayer);
            }
        }

        if (exactLayer.isEmpty()) {
            String focused = findFocusedComponent(safePkg);
            String list = exec("dumpsys SurfaceFlinger --list");
            String selected = selectExactGameLayer(list, safePkg, focused);
            if (!selected.isEmpty()) {
                synchronized (this) {
                    cachedPackage = safePkg;
                    cachedLayer = selected;
                    exactFocusedComponent = focused;
                    exactLayerFailures = 0;
                    exactLayerSelectedAtMs = System.currentTimeMillis();
                }
                // Igual que SysFloat: limpiar el historial al seleccionar la capa,
                // pero no en cada lectura, para poder medir una ventana real.
                exec("dumpsys SurfaceFlinger --latency-clear");
                lastStatus = "FPS exacto • capa CODM detectada, preparando" + shellSuffix();
                lastLayer = shortLayer(selected);
            }
        }

        // Respaldo 1: TimeStats asociado al paquete/capa CODM.
        ensureTimeStats();
        long now = System.currentTimeMillis();
        String timeHint = "TimeStats capturando";
        if (timeStatsEnabled && now - timeStatsStartedAt >= 1600L) {
            String timeDump = exec("dumpsys SurfaceFlinger --timestats -dump");
            TimeStatsResult ts = parseTimeStats(timeDump, safePkg);
            String restart = exec("dumpsys SurfaceFlinger --timestats -clear -enable");
            timeStatsStartedAt = System.currentTimeMillis();
            if (looksLikeError(restart)) {
                timeHint = "TimeStats reinicio: " + firstLine(restart);
            } else if (ts.fps > 0) {
                lastStatus = "FPS respaldo • TimeStats CODM" + shellSuffix();
                lastLayer = shortLayer(ts.layer);
                return (float) ts.fps;
            } else if (timeDump == null || timeDump.trim().isEmpty()) {
                timeHint = "TimeStats vacío";
            } else if (looksLikeError(timeDump)) {
                timeHint = "TimeStats: " + firstLine(timeDump);
            } else {
                timeHint = "TimeStats sin FPS CODM";
            }
        }

        // Respaldo 2: FrameCompleted del proceso del juego.
        int gfx = parseGfxInfoFps(exec("dumpsys gfxinfo " + safePkg + " framestats"));
        if (gfx > 0) {
            lastStatus = "FPS respaldo • gfxinfo CODM" + shellSuffix();
            lastLayer = "gfxinfo";
            return (float) gfx;
        }

        // Respaldo 3: contador OEM/kernel. Puede representar display, por eso no es principal.
        int kernelFps = readKernelFps();
        if (kernelFps > 0) return (float) kernelFps;

        // Últimos respaldos globales para ROMs donde la capa está oculta.
        float globalLatency = parseSurfaceFlingerFpsExact(exec("dumpsys SurfaceFlinger --latency"));
        if (globalLatency > 0f) {
            lastStatus = "FPS respaldo • SurfaceFlinger global" + shellSuffix();
            lastLayer = "display/global";
            return globalLatency;
        }

        int pageFlipFps = readPageFlipFps();
        if (pageFlipFps > 0) {
            lastStatus = "FPS respaldo • page flips global" + shellSuffix();
            return (float) pageFlipFps;
        }

        lastStatus = "Sin FPS • " + timeHint + shellSuffix();
        return -1f;
    }

    private String findFocusedComponent(String pkg) {
        Pattern component = Pattern.compile(Pattern.quote(pkg) + "/([A-Za-z0-9_.$]+)");
        String out = exec("dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp' | head -6");
        Matcher m = component.matcher(out == null ? "" : out);
        if (m.find()) return pkg + "/" + m.group(1);
        out = exec("dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity' | head -6");
        m = component.matcher(out == null ? "" : out);
        if (m.find()) return pkg + "/" + m.group(1);
        return "";
    }

    private static String selectExactGameLayer(String data, String pkg, String focusedComponent) {
        if (data == null || data.trim().isEmpty()) return "";
        String lpkg = pkg.toLowerCase(Locale.ROOT);
        String lcomp = focusedComponent == null ? "" : focusedComponent.toLowerCase(Locale.ROOT);
        String activity = "";
        int slash = lcomp.indexOf('/');
        if (slash >= 0 && slash + 1 < lcomp.length()) activity = lcomp.substring(slash + 1);

        String best = "";
        int bestScore = Integer.MIN_VALUE;
        Set<String> seen = new LinkedHashSet<>();
        for (String raw : data.split("\\r?\\n")) {
            String line = raw == null ? "" : raw.trim();
            if (line.isEmpty() || !seen.add(line)) continue;
            String l = line.toLowerCase(Locale.ROOT);
            boolean belongs = l.contains(lpkg) || l.contains("callofduty") || l.contains("call of duty") || l.contains("codm");
            boolean renderSurface = l.contains("surfaceview") || l.contains("blast");
            if (!belongs || !renderSurface) continue;

            int score = 100;
            if (l.contains(lpkg)) score += 300;
            if (l.contains("surfaceview")) score += 500;
            if (l.contains("blast")) score += 400;
            if (!lcomp.isEmpty() && l.contains(lcomp)) score += 450;
            if (!activity.isEmpty() && l.contains(activity)) score += 220;
            if (l.contains("#0")) score += 30;
            if (l.contains("mainactivity")) score += 50;
            if (l.contains("activityrecord")) score -= 700;
            if (l.contains("splash")) score -= 800;
            if (l.contains("snapshot")) score -= 700;
            if (l.contains("starting")) score -= 500;
            if (score > bestScore) {
                bestScore = score;
                best = line;
            }
        }
        return best;
    }

    private float readLayerFpsExact(String layer) {
        if (layer == null || layer.trim().isEmpty()) return -1f;
        String latency = exec("dumpsys SurfaceFlinger --latency " + shellQuote(layer.trim()));
        return parseSurfaceFlingerFpsExact(latency);
    }

    static float parseSurfaceFlingerFpsExact(String data) {
        if (data == null || data.trim().isEmpty()) return -1f;
        String[] lines = data.split("\\r?\\n");
        List<Long> actualPresent = new ArrayList<>();

        // SurfaceFlinger --latency: primera línea = refresh period.
        // Filas: desiredPresentTime, actualPresentTime, frameReadyTime.
        // FPS visible = actualPresentTime (segunda columna, índice 1).
        for (int i = 1; i < lines.length; i++) {
            String line = lines[i] == null ? "" : lines[i].trim();
            if (line.isEmpty()) continue;
            String[] p = line.split("\\s+");
            if (p.length < 2) continue;
            try {
                long t = Long.parseLong(p[1]);
                if (t > 0L && t < 9_000_000_000_000_000_000L) actualPresent.add(t);
            } catch (Throwable ignored) { }
        }
        if (actualPresent.size() < 8) return -1f;

        Collections.sort(actualPresent);
        List<Long> unique = new ArrayList<>(actualPresent.size());
        long prev = Long.MIN_VALUE;
        for (long t : actualPresent) {
            if (t != prev) unique.add(t);
            prev = t;
        }
        if (unique.size() < 8) return -1f;

        long newest = unique.get(unique.size() - 1);
        long cutoff = newest - 1_100_000_000L;
        int first = 0;
        while (first < unique.size() - 2 && unique.get(first) < cutoff) first++;
        int count = unique.size() - first;
        if (count < 8) return -1f;
        long oldest = unique.get(first);
        double seconds = (newest - oldest) / 1_000_000_000.0;
        if (seconds < 0.10 || seconds > 1.30) return -1f;
        double fps = (count - 1) / seconds;
        if (fps < 1.0 || fps > 300.0) return -1f;
        return (float)(Math.round(fps * 10.0) / 10.0);
    }

'''
c = c[:read_start] + new_read + c[read_end:]
client.write_text(c)

service = root / 'app/src/main/java/com/codm/crosshair/CodmAccessibilityService.java'
t = service.read_text()
t = t.replace('        int fps = -1;', '        float fps = -1f;', 1)
t = t.replace('        final int f = fps;', '        final float f = fps;', 1)

old_ui = '                s.append(f >= 0 ? f : "—").append(" FPS");'
new_ui = '                if (f >= 0f) s.append(String.format(java.util.Locale.US, "%.1f", f));\n                else s.append("—");\n                s.append(" FPS");'
if old_ui not in t:
    raise SystemExit('No se encontró salida visual FPS')
t = t.replace(old_ui, new_ui, 1)

old_pref = 'prefs.edit().putInt("last_fps", f).putInt("last_battery", b).putInt("last_battery_temp_tenths", t10)'
new_pref = 'prefs.edit().putInt("last_fps", f >= 0f ? Math.round(f) : -1).putFloat("last_fps_exact", f).putInt("last_battery", b).putInt("last_battery_temp_tenths", t10)'
if old_pref not in t:
    raise SystemExit('No se encontró guardado last_fps')
t = t.replace(old_pref, new_pref, 1)

pattern = r'    private int stabilizeFps\(int rawFps\) \{.*?^    \}\n\n    private int currentRefreshRateCap\(\) \{'
replacement = '''    private float stabilizeFps(float rawFps) {
        if (rawFps < 1f) return -1f;
        int refreshCap = currentRefreshRateCap();
        float cap = refreshCap > 0 ? Math.min(120.0f, (float) refreshCap) : 120.0f;
        float result = Math.min(rawFps, cap);
        return Math.round(result * 10f) / 10f;
    }

    private int currentRefreshRateCap() {'''
t, n = re.subn(pattern, replacement, t, count=1, flags=re.S | re.M)
if n != 1:
    raise SystemExit('No se encontró stabilizeFps')

old_hz = 'if (hz >= 30f && hz <= 360f) return Math.max(1, Math.round(hz));'
new_hz = 'if (hz >= 30f && hz <= 360f) return Math.min(120, Math.max(1, Math.round(hz)));'
if old_hz not in t:
    raise SystemExit('No se encontró lectura Hz')
t = t.replace(old_hz, new_hz, 1)
service.write_text(t)

main = root / 'app/src/main/java/com/codm/crosshair/MainActivity.java'
mt = main.read_text().replace('CODM CROSSHAIR AUTO • v16', 'CODM CROSSHAIR AUTO • v20')
main.write_text(mt)

# Validaciones del transformador antes de compilar.
assert 'versionCode 20' in gradle.read_text()
assert 'FPS EXACTO • SurfaceView/BLAST CODM' in client.read_text()
assert 'actualPresentTime' in client.read_text()
assert 'float stabilizeFps(float rawFps)' in service.read_text()
assert '"%.1f"' in service.read_text()
