// Countdown -- runs entirely on the BUSY Bar, launched from the APPS menu.
//
//   open it        -> a 3:00 countdown starts immediately
//   reaches zero   -> plays a sound, then keeps counting UP as "+M:SS" so you
//                     can see by how much you ran over
//   open it again  -> starts over at 3:00
//
// Getting back to the menu takes some care on firmware 1.2.3:
//
//   * Picking an app in the APPS menu saves its id as `active_application`,
//     and apps_menu_alloc() *resumes* that app when it is next entered with no
//     argument, instead of showing the list. So leaving the launcher bounces
//     straight back into this app -- the screen blinks and the timer returns.
//     This app clears that setting on startup to break the loop; apps_menu
//     re-reads the file when it comes back and never rewrites it on exit.
//
//   * js_app_launcher's run scene also handles the Back event with a literal
//     `// TODO: Special Back key treatment?`, so do not rely on BACK alone.
//     A script's own reliable exit is *finishing*: once no interval or fetch
//     is pending, js_runner fires its termination callback and the launcher
//     returns to the menu. Hence the overtime limit below.
//
// The JerryScript runtime exposes only console, timers, fetch and
// localStorage -- there is no input binding, so the app takes no input beyond
// being launched. Everything on screen is drawn by POSTing to the device's own
// HTTP API, exactly as a host-side app would.

var APP = "app.busy.countdown";

// Change these and reinstall to use different lengths.
var DURATION_SECONDS = 180; // 3:00
// How long to keep showing the overrun before quitting back to the menu.
var OVERTIME_LIMIT_SECONDS = 300; // 5:00

var WIDTH = 72;
var TICK_MS = 250;

// Elements expire on their own, so nothing is left over the APPS menu after
// BACK. Kept just above the redraw interval below.
var ELEMENT_TIMEOUT = 2;
var HEARTBEAT_MS = 800;

var GREEN = "#00FF66FF";
var AMBER = "#FFAA00FF";
var RED = "#FF2200FF";
var TRACK = "#181818FF";
var OFF = "#00000000";

var SOUND = "shared/sounds/calendar_reminder_ends.snd";
var MENU_SETTINGS = "/ext/apps_data/apps_menu/settings.json";

// The shipped example hardcodes the USB-ethernet address, which only exists
// while USB is plugged in. Probe loopback first and fall back to it.
var API_CANDIDATES = ["http://127.0.0.1/api", "http://10.0.4.20/api"];
var API = null;

var startMs = null; // wall clock start, when Date is available
var ticks = 0; // fallback: counted intervals
var soundPlayed = false;
var lastKey = null;
var lastDrawMs = 0;
var intervalId = null;
var finished = false;

function nowMs() {
    if (typeof Date !== "undefined" && Date.now) {
        return Date.now();
    }
    return null;
}

function elapsedSeconds() {
    if (startMs !== null) {
        return (Date.now() - startMs) / 1000;
    }
    return ticks * TICK_MS / 1000;
}

function post(path, body) {
    return fetch(new Request(API + path, {
        method: "POST",
        body: JSON.stringify(body),
    }));
}

function twoDigit(n) {
    return n < 10 ? "0" + n : String(n);
}

// Countdown rounds up so the last whole second is shown for a full second;
// overtime rounds down so it reads "+0" the instant it goes over.
function formatClock(seconds, roundUp) {
    var t = roundUp ? Math.ceil(seconds - 0.0001) : Math.floor(seconds);
    if (t < 0) t = 0;
    var hours = Math.floor(t / 3600);
    var minutes = Math.floor((t % 3600) / 60);
    var secs = t % 60;
    if (hours > 0) {
        return hours + ":" + twoDigit(minutes) + ":" + twoDigit(secs);
    }
    return minutes + ":" + twoDigit(secs);
}

function draw(digits, digitColor, barColor, barWidth) {
    return post("/display/draw", {
        application_name: APP,
        priority: 50,
        elements: [
            {
                id: "track", type: "rectangle",
                x: 0, y: 13, width: WIDTH, height: 3,
                fill: "solid", fill_colors: [TRACK], border_width: 0,
                z_index: 0, display: "front", timeout: ELEMENT_TIMEOUT,
            },
            {
                id: "bar", type: "rectangle",
                // `width` has a minimum of 1 in the API schema.
                x: 0, y: 13, width: Math.max(1, barWidth), height: 3,
                fill: "solid", fill_colors: [barColor], border_width: 0,
                z_index: 1, display: "front", timeout: ELEMENT_TIMEOUT,
            },
            {
                id: "digits", type: "text",
                text: digits, font: "extra_large", color: digitColor,
                align: "center", x: 36, y: 5,
                z_index: 2, display: "front", timeout: ELEMENT_TIMEOUT,
            },
        ],
    }).catch(function (e) {
        console.error("draw failed:", e);
    });
}

function playSound() {
    post("/audio/play", {
        application_name: APP,
        stock_path: SOUND,
    }).catch(function (e) {
        console.error("sound failed:", e);
    });
}

// Stop the APPS menu from relaunching this app the moment we leave it.
function releaseMenuResume() {
    return fetch(API + "/storage/read?path=" + MENU_SETTINGS)
        .then(function (response) { return response.json(); })
        .then(function (settings) {
            if (!settings || !settings.values) return null;
            if (settings.values.active_application === "") return null;
            settings.values.active_application = "";
            return fetch(new Request(API + "/storage/write?path=" + MENU_SETTINGS, {
                method: "POST",
                body: JSON.stringify(settings),
            }));
        })
        .catch(function (error) {
            console.error("could not clear active_application:", error);
        });
}


// Ending every background task is what tells js_runner the script is done,
// which is what returns the launcher to the APPS menu.
function finish() {
    if (finished) return;
    finished = true;
    if (intervalId !== null) {
        clearInterval(intervalId);
        intervalId = null;
    }
    console.info("Countdown: overtime limit reached, returning to the menu");
}


function render() {
    var elapsed = elapsedSeconds();
    var remaining = DURATION_SECONDS - elapsed;
    var digits, digitColor, barColor, barWidth, key;

    if (remaining > 0) {
        digits = formatClock(remaining, true);
        var fraction = remaining / DURATION_SECONDS;
        digitColor = (remaining <= 5 || fraction <= 0.2)
            ? RED
            : (fraction > 0.5 ? GREEN : AMBER);
        barColor = digitColor;
        barWidth = Math.round(WIDTH * fraction);
        key = digits + digitColor + barWidth;
    } else {
        var over = -remaining;
        if (over >= OVERTIME_LIMIT_SECONDS) {
            finish();
            return;
        }
        if (!soundPlayed) {
            soundPlayed = true;
            playSound();
        }
        digits = "+" + formatClock(over, false);
        // Flash for the first 2s so the moment it expires is unmissable,
        // then hold steady red rather than blinking for minutes on end.
        var lit = over > 2 || Math.floor(over * 2) % 2 === 0;
        digitColor = lit ? RED : OFF;
        barColor = lit ? RED : OFF;
        barWidth = WIDTH;
        key = digits + digitColor;
    }

    var timestamp = nowMs();
    var stale = timestamp === null || (timestamp - lastDrawMs) >= HEARTBEAT_MS;
    if (key !== lastKey || stale) {
        lastKey = key;
        if (timestamp !== null) lastDrawMs = timestamp;
        draw(digits, digitColor, barColor, barWidth);
    }
}

function tick() {
    if (finished) return;
    ticks++;
    render();
}

function start() {
    releaseMenuResume();
    startMs = nowMs();
    if (startMs === null) {
        console.info("Countdown: no Date built-in, counting interval ticks");
    }
    render(); // paint 3:00 immediately rather than after the first tick
    intervalId = setInterval(tick, TICK_MS);
}

function probe(index) {
    if (index >= API_CANDIDATES.length) {
        console.error("Countdown: no reachable API base, giving up");
        return;
    }
    fetch(API_CANDIDATES[index] + "/version")
        .then(function (response) { return response.json(); })
        .then(function (version) {
            API = API_CANDIDATES[index];
            console.info(
                "Countdown: " + DURATION_SECONDS + "s via " + API +
                " (api " + version.api_semver + ")"
            );
            start();
        })
        .catch(function () { probe(index + 1); });
}

probe(0);
