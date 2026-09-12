ObjC.import('Foundation');
var path = '/Users/witwash/Projects/busy_countdown/apps/device/app.busy.countdown/scripts/main.js';
var src = ObjC.unwrap($.NSString.stringWithContentsOfFileEncodingError(path, $.NSUTF8StringEncoding, null));

var out = [], drawCalls = [], soundCalls = 0, intervalFn = null, fakeNow = 1000000, ok = true;
function log(s){ out.push(s); }
function chk(label, got, want){
  var good = String(got) === String(want);
  if (!good) ok = false;
  log((good ? 'ok   ' : 'FAIL ') + label + ': ' + got + (good ? '' : ' != ' + want));
}

globalThis.console = { log:function(){}, info:function(){}, error:function(a,b){ log('console.error: '+a); } };
globalThis.Request = function(url, opts){ this.url = url; this.opts = opts; };
globalThis.setInterval = function(fn){ intervalFn = fn; return 42; };
var clearedId = null;
globalThis.clearInterval = function(id){ clearedId = id; intervalFn = null; };
globalThis.Date = { now: function(){ return fakeNow; } };
// Synchronous thenable: JXA does not drain the microtask queue inside one
// osascript pass, so real Promises would leave the chains unresolved.
function thenable(value){
  return {
    then: function(onFulfilled){
      var r;
      try { r = onFulfilled ? onFulfilled(value) : value; } catch(e){ return thenable(undefined); }
      return (r && typeof r.then === 'function') ? r : thenable(r);
    },
    catch: function(){ return this; }
  };
}

// Stands in for the device's stored APPS-menu settings.
var deviceSettings = { version: 1, values: { active_application: 'app.busy.countdown' } };
var settingsWrites = 0;

globalThis.fetch = function(req){
  var url = (typeof req === 'string') ? req : req.url;
  if (url.indexOf('/version') !== -1)
    return thenable({ json: function(){ return thenable({api_semver:'27.5.0'}); } });
  if (url.indexOf('/storage/read') !== -1)
    return thenable({ json: function(){ return thenable(JSON.parse(JSON.stringify(deviceSettings))); } });
  if (url.indexOf('/storage/write') !== -1) {
    settingsWrites++;
    deviceSettings = JSON.parse(req.opts.body);
    return thenable({ json: function(){ return thenable({result:'OK'}); } });
  }
  if (url.indexOf('/display/draw') !== -1) drawCalls.push(JSON.parse(req.opts.body));
  else if (url.indexOf('/audio/play') !== -1) soundCalls++;
  return thenable({ json: function(){ return thenable({result:'OK'}); } });
};

try { (0,eval)(src); } catch (e) { log('SYNTAX ERROR: ' + e); ok = false; }

function lastDraw(){
  var d = drawCalls[drawCalls.length-1];
  var els = {};
  d.elements.forEach(function(e){ els[e.id] = e; });
  return els;
}
function advance(seconds){ fakeNow += seconds*1000; render(); }

// probe() completes on the microtask queue, which does not drain inside a
// single osascript pass -- do what it would have done and start directly.
API = 'http://127.0.0.1/api';
start();

if (drawCalls.length === 0) { log('FAIL: nothing drawn after launch'); ok = false; }
else {
  chk('format 180s', formatClock(180, true), '3:00');
  chk('format 65s',  formatClock(65, true),  '1:05');
  chk('format 5s',   formatClock(5, true),   '0:05');
  chk('format 3600s',formatClock(3600,true), '1:00:00');
  chk('overtime 0.4s floor', formatClock(0.4, false), '0:00');
  chk('overtime 7s', formatClock(7, false),  '0:07');

  // the APPS menu must not be left pointing at this app, or leaving it
  // relaunches straight back in
  chk('cleared active_application', deviceSettings.values.active_application, '');
  chk('settings written once', settingsWrites, 1);
  chk('kept other settings keys', deviceSettings.version, 1);

  chk('first frame digits', lastDraw().digits.text, '3:00');
  chk('first frame colour', lastDraw().digits.color, '#00FF66FF');
  chk('first frame bar',    lastDraw().bar.width, 72);
  chk('element timeout',    lastDraw().digits.timeout, 2);
  chk('no sound yet',       soundCalls, 0);

  advance(90);  chk('at 90s digits', lastDraw().digits.text, '1:30');
  chk('at 90s amber-ish', lastDraw().digits.color, '#FFAA00FF');
  chk('at 90s bar', lastDraw().bar.width, 36);

  advance(54);  chk('at 144s digits', lastDraw().digits.text, '0:36');
  chk('at 144s red (<=20%)', lastDraw().digits.color, '#FF2200FF');

  advance(35);  chk('at 179s digits', lastDraw().digits.text, '0:01');
  chk('still silent', soundCalls, 0);

  advance(1);   // exactly 180 -> overtime
  chk('sound fired once', soundCalls, 1);
  chk('overtime digits', lastDraw().digits.text, '+0:00');
  chk('overtime bar full', lastDraw().bar.width, 72);

  advance(7);   chk('overtime +0:07', lastDraw().digits.text, '+0:07');
  chk('steady red after flash', lastDraw().digits.color, '#FF2200FF');
  chk('sound not repeated', soundCalls, 1);

  advance(113); chk('overtime +2:00', lastDraw().digits.text, '+2:00');
  chk('sound still once', soundCalls, 1);
  chk('not exited before limit', clearedId, 'null');

  // crossing OVERTIME_LIMIT_SECONDS must stop every background task, which is
  // what makes js_runner return the launcher to the APPS menu
  var beforeExit = drawCalls.length;
  advance(179);  // 120 + 179 = 299s overtime, still under the 300s limit
  chk('still running at +4:59', clearedId, 'null');
  advance(1);    // 300s -> exit
  chk('cleared the interval', clearedId, 42);
  chk('kept drawing up to the limit', drawCalls.length > beforeExit, 'true');
  var afterExit = drawCalls.length;
  if (intervalFn) intervalFn();
  chk('no further ticks after exit', drawCalls.length, afterExit);

  // ASCII-only and colour format, per the display API
  var d = lastDraw();
  chk('digits ascii', /^[\x20-\x7E]+$/.test(d.digits.text), 'true');
  chk('colour 8 hex', /^#[0-9A-Fa-f]{8}$/.test(d.digits.color), 'true');
  chk('bar width >=1', d.bar.width >= 1, 'true');
}
log(ok ? '\nALL PASS' : '\nFAILURES');
out.join('\n');
