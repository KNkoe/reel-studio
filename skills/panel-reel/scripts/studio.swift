// "Studio" look for the face camera, on-device (Apple Vision + Core Image), no uploads.
//
//   studio <face.mp4> <settings.json> | ffmpeg -f rawvideo -pix_fmt bgra ...     (every frame)
//     The alpha channel is the speaker's outline, so one pass feeds both the graded video and
//     the head cut-out: one outline, identical colours, no seam between the two layers.
//   studio <face.mp4> <settings.json> --stills 90,600 <dir>                      (test frames)
//
//   room    : either a rendered studio set ("backdrop", see studio_set.py; a still, or a video that
//             loops) in place of the wall,
//             or the real wall: lens blur, about a stop darker, a pool behind the head, practicals
//   skin    : evened and smoothed (spots and shine), keeping some pore texture; eyes, brows,
//             lips, beard and clothing are left sharp
//   speaker : soft key light that follows the face, thin rim light on the shadow side,
//             light denoise, local contrast and sharpening
//   match   : puts the speaker under the colour of a rendered room's light (off unless asked)
//   gold    : a copper-gold grade over the whole picture, rebuilt layer by layer from a
//             Photoshop adjustment stack (see goldGrade below)
//   finish  : gentle toe and highlight shoulder, a faint bloom and fine grain
// It only reshapes light and colour in the real footage. It does not redraw the face.
import AVFoundation
import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

struct Settings: Decodable {
    var backdrop = ""        // image that replaces the wall behind the speaker; empty keeps the real room
    var matte = ""           // grey video of the speaker's outline (rvm_matte.py), or the ".csv" list of its parts
                             // while it is still being made; empty uses Apple's per-frame mask
    var blur = 11.0          // background lens blur radius, px
    var wall = 0.36          // background exposure in linear light (1 = untouched)
    var pool = 0.85          // extra light on the wall behind the head
    var warm = [0.92, 0.46, 0.12]   // practical on the left of frame (sRGB 0-1)
    var cool = [0.16, 0.36, 0.52]   // fill on the right of frame
    var practical = 0.60     // strength of both coloured lights
    var gold = 1.0           // copper-gold grade (0 = off, 1 = the full layer stack)
    var selective = 0.5      // its red and yellow layer: 0.5 for a well-lit face, 1 for a dark, moody one
    var key = 0.26           // key light on the face
    var rim = 0.24           // rim light on the speaker's edges
    var bloom = 0.07         // highlight diffusion
    var grain = 1.1          // in 8-bit code values
    var skin = 0.82          // skin retouch strength (0 = off, 1 = full)
    var gate = true          // false trusts the video outline where Apple's mask drops part of the speaker
    var relight = 1.0        // reshaping of light on the speaker; 0 keeps the light as shot (use with key and rim 0)

    var match = 0.0          // how strongly the speaker takes the room's light (0 = as shot)
    var ambient = [0.5, 0.5, 0.5]       // the room's bounce light (sRGB 0-1)
    var windowLight = [0.9, 0.9, 0.9]   // daylight from the window side
    var lampLight = [0.9, 0.8, 0.7]     // the lamp on the other side
    var windowRight = false

    init() {}
    enum K: String, CodingKey { case backdrop, matte, blur, wall, pool, warm, cool, practical, key, rim, bloom, grain, skin, gold, selective, relight, gate, match, ambient, windowLight, lampLight, windowRight }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: K.self)
        func value<T: Decodable>(_ k: K, _ fallback: T) throws -> T { try c.decodeIfPresent(T.self, forKey: k) ?? fallback }
        backdrop = try value(.backdrop, backdrop)
        matte = try value(.matte, matte)
        blur = try value(.blur, blur); wall = try value(.wall, wall); pool = try value(.pool, pool)
        warm = try value(.warm, warm); cool = try value(.cool, cool); practical = try value(.practical, practical)
        key = try value(.key, key); rim = try value(.rim, rim); bloom = try value(.bloom, bloom); grain = try value(.grain, grain); skin = try value(.skin, skin)
        gold = try value(.gold, gold); selective = try value(.selective, selective)
        relight = try value(.relight, relight)
        gate = try value(.gate, gate)
        match = try value(.match, match); ambient = try value(.ambient, ambient)
        windowLight = try value(.windowLight, windowLight); lampLight = try value(.lampLight, lampLight)
        windowRight = try value(.windowRight, windowRight)
    }
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!); exit(2)
}

let metal = """
#include <CoreImage/CoreImage.h>
using namespace metal;

static float3 toLinear(float3 c) { return pow(max(c, 0.0), float3(2.2)); }
static float3 toCode(float3 c) { return pow(max(c, 0.0), float3(1.0 / 2.2)); }
static float blob(float2 p, float2 centre, float2 radius) {
    float2 d = (p - centre) / radius;
    return exp(-dot(d, d));
}

// Where there is bare skin: warm, saturated, mid-toned. Pale caps, pearls, teeth, black cloth
// and beard hair all fall outside it; eyes, brows and lips arrive already cut out of "allow".
[[ stitchable ]] float4 skinWeight(coreimage::sample_t ref, coreimage::sample_t allow) {
    float3 c = ref.rgb;
    float high = max(c.r, max(c.g, c.b)), low = min(c.r, min(c.g, c.b));
    float sat = (high - low) / max(high, 0.001);
    float luma = dot(c, float3(0.2126, 0.7152, 0.0722));
    float w = clamp(allow.r, 0.0, 1.0) * smoothstep(0.23, 0.37, sat) * smoothstep(0.07, 0.17, luma)
            * smoothstep(0.02, 0.08, c.r - c.b) * (1.0 - smoothstep(0.86, 0.95, luma));
    return float4(w, w, w, 1.0);
}

[[ stitchable ]] float4 weighted(coreimage::sample_t image, coreimage::sample_t weight) {
    return float4(image.rgb * weight.r, weight.r);
}

// Edge-preserving smooth. The reference is already softened, so a small spot cannot protect itself.
[[ stitchable ]] float4 bilateral(coreimage::sampler source, coreimage::sampler reference, float radius,
                                  float sigma, coreimage::destination dest) {
    float2 d = dest.coord();
    float3 centre = reference.sample(reference.transform(d)).rgb;
    float3 sum = float3(0.0);
    float total = 0.0;
    for (int y = -6; y <= 6; y++) {
        for (int x = -6; x <= 6; x++) {
            float2 step = float2(x, y);
            float3 c = source.sample(source.transform(d + step * radius / 6.0)).rgb;
            float3 diff = c - centre;
            float w = exp(-dot(step, step) / 22.0 - dot(diff, diff) / (2.0 * sigma * sigma));
            sum += c * w;
            total += w;
        }
    }
    return float4(sum / max(total, 0.0001), 1.0);
}

[[ stitchable ]] float4 retouch(coreimage::sample_t base, coreimage::sample_t clean, coreimage::sample_t smooth,
                                coreimage::sample_t fine, coreimage::sample_t tone, coreimage::sample_t weight,
                                float strength) {
    float3 even = smooth.rgb;
    if (tone.a > 0.02) {
        float3 around = tone.rgb / tone.a;
        even += clamp(around - even, 0.0, 0.10) * 0.62;          // lift dark spots and marks
        even -= max(even - around - 0.050, 0.0) * 0.14;          // calm hot spots, keep the glow
    }
    // pores come back from the untouched footage; the limit stops marks coming back with them
    even += clamp(clean.rgb - fine.rgb, -0.028, 0.028) * 0.80;
    return float4(mix(base.rgb, even, clamp(weight.r * strength, 0.0, 1.0)), 1.0);
}

static float lum(float3 c) { return dot(c, float3(0.30, 0.59, 0.11)); }
static float3 setLum(float3 c, float target) {                       // Photoshop "Luminosity"
    c += target - lum(c);
    float l = lum(c), low = min(c.r, min(c.g, c.b)), high = max(c.r, max(c.g, c.b));
    if (low < 0.0) c = l + (c - l) * l / max(l - low, 0.0001);
    if (high > 1.0) c = l + (c - l) * (1.0 - l) / max(high - l, 0.0001);
    return clamp(c, 0.0, 1.0);
}
static float softLight(float base, float top) {                       // Photoshop "Soft Light"
    float d = base <= 0.25 ? ((16.0 * base - 12.0) * base + 4.0) * base : sqrt(base);
    return top <= 0.5 ? base - (1.0 - 2.0 * top) * base * (1.0 - base)
                      : base + (2.0 * top - 1.0) * (d - base);
}

// The copper-gold recipe, bottom layer first. "selective" is the one layer turned down for brighter faces.
// Like adjustment layers it covers the whole picture; selective colour picks out skin by its hue.
[[ stitchable ]] float4 goldGrade(coreimage::sample_t image, float amount, float selective) {
    float3 c = clamp(image.rgb, 0.0, 1.0);

    // 1. gradient map "Copper 1", soft light, 30%
    float l = lum(c);
    float3 stop[5] = { float3(27, 19, 20), float3(90, 61, 59), float3(147, 114, 108),
                       float3(208, 186, 178), float3(247, 233, 229) };
    float at = clamp(l, 0.0, 1.0) * 4.0;
    int i = min(int(at), 3);
    float3 map = mix(stop[i], stop[i + 1], at - float(i)) / 255.0;
    float3 toned = float3(softLight(c.r, map.r), softLight(c.g, map.g), softLight(c.b, map.b));
    c = mix(c, toned, 0.30 * amount);

    // 2. black and white "Blue Filter" (reds, yellows, greens 0; cyans, blues, magentas 110),
    //    luminosity, 30%. Blend If fades it evenly from the shadows to nothing at white.
    float high = max(c.r, max(c.g, c.b)), low = min(c.r, min(c.g, c.b));
    float middle = c.r + c.g + c.b - high - low;
    float primary = (c.b >= high - 0.0001) ? 1.1 : 0.0;
    float secondary = (c.b <= low + 0.0001) ? 0.0 : 1.1;
    float grey = clamp(low + (middle - low) * secondary + (high - middle) * primary, 0.0, 1.0);
    l = lum(c);
    c = setLum(c, mix(l, grey, 0.30 * amount * (1.0 - l)));

    // 3. selective colour (relative): reds cyan -50 yellow +30; yellows cyan -20 yellow -50;
    //    neutrals black +5
    high = max(c.r, max(c.g, c.b)); low = min(c.r, min(c.g, c.b)); middle = c.r + c.g + c.b - high - low;
    float reds = c.r >= high - 0.0001 ? high - middle : 0.0;
    float yellows = c.b <= low + 0.0001 ? middle - low : 0.0;
    float neutrals = clamp(1.0 - (abs(high - 0.5) + abs(low - 0.5)), 0.0, 1.0);
    float3 before = c;
    float k = amount * selective;
    c.r += (0.50 * reds + 0.20 * yellows) * (1.0 - before.r) * k;
    c.b += (-0.30 * reds + 0.50 * yellows) * (1.0 - before.b) * k;
    c -= 0.05 * neutrals * (1.0 - before) * k;
    c = clamp(c, 0.0, 1.0);

    // 4. gradient map "Platinum" with its dark stop moved to 50%, luminosity, 20%, same Blend If
    l = lum(c);
    float platinum = clamp((l - 0.5) * 2.0, 0.0, 1.0) * 0.955;
    c = setLum(c, mix(l, platinum, 0.20 * amount * (1.0 - l)));

    // 5. curve: the lit side of the skin up a little, the shaded side down
    float3 bent = c - 0.026 * exp(-pow((c - 0.25) / 0.14, 2.0)) + 0.046 * exp(-pow((c - 0.62) / 0.18, 2.0));
    return float4(clamp(mix(c, bent, amount), 0.0, 1.0), 1.0);
}

// The room without the speaker, weighted, so the blur never smears skin into the wall.
[[ stitchable ]] float4 plate(coreimage::sample_t image, coreimage::sample_t hole) {
    float keep = 1.0 - clamp(hole.r, 0.0, 1.0);
    return float4(toLinear(image.rgb) * keep, keep);
}

[[ stitchable ]] float4 light(coreimage::sample_t soft, coreimage::sample_t wide, coreimage::sample_t person,
                              coreimage::sample_t matte, coreimage::sample_t inner, coreimage::sample_t core,
                              coreimage::sample_t leftOf, coreimage::sample_t rightOf, coreimage::sample_t backdrop,
                              float useSet, float2 size, float2 face, float faceSize, float wall, float pool,
                              float3 warm, float3 cool, float practical, float key, float rim, float relight,
                              coreimage::destination dest) {
    float2 p = dest.coord();
    float2 uv = p / size;
    float m = clamp(matte.r, 0.0, 1.0);

    // room
    float3 room = soft.a > 0.02 ? soft.rgb / soft.a : wide.rgb / max(wide.a, 0.001);
    float grey = dot(room, float3(0.2126, 0.7152, 0.0722));
    room = mix(float3(grey), room, 0.55);
    float behind = blob(p, face + float2(0.0, faceSize * 0.15), float2(faceSize * 1.55, faceSize * 1.45));
    float edge = distance(uv * float2(1.0, 0.9), face / size * float2(1.0, 0.9));
    float falloff = mix(1.0, 0.34, smoothstep(0.22, 0.72, edge));
    float3 lit = room * wall * falloff * (1.0 + pool * behind);
    float left = blob(uv, float2(0.02, 0.66), float2(0.30, 0.50));
    float right = blob(uv, float2(1.00, 0.50), float2(0.28, 0.55));
    float3 amber = toLinear(warm), teal = toLinear(cool);
    lit = lit * mix(float3(1.0), amber * 2.1 + 0.25, left * 0.75 * practical) + amber * 0.060 * left * practical;
    lit = lit * mix(float3(1.0), teal * 2.1 + 0.45, right * 0.60 * practical) + teal * 0.030 * right * practical;

    // a rendered set arrives already lit and blurred; it only gains a little light behind the head
    if (useSet > 0.5) lit = toLinear(backdrop.rgb) * (1.0 + 0.16 * behind);

    // speaker
    float3 skin = toLinear(person.rgb);
    // Old wall light clings to the outline: an edge pixel may not outshine what sits just inside it.
    if (inner.a > 0.02) {
        float3 inside = inner.rgb / inner.a;
        float band = 1.0 - smoothstep(0.55, 0.98, core.r);
        skin = mix(skin, min(skin, inside * 1.10 + 0.006), band);
    }
    float keyLight = blob(p, face + float2(faceSize * 0.22, faceSize * 0.12), float2(faceSize * 0.80, faceSize * 0.95));
    float chest = smoothstep(face.y - faceSize * 0.75, face.y - faceSize * 1.75, p.y);
    float side = smoothstep(0.25, 1.15, abs(p.x - face.x) / faceSize);
    skin *= mix(1.0, (0.93 + key * keyLight) * (1.0 - 0.30 * chest) * (1.0 - 0.12 * side), relight);
    // roll off hot spots on the skin so the light stays rich instead of washing out
    float bright = dot(skin, float3(0.2126, 0.7152, 0.0722));
    float warmth = smoothstep(0.06, 0.20, person.r - person.b);        // skin, not the pale cap
    if (bright > 0.26) skin *= mix(1.0, (0.26 + 0.20 * tanh((bright - 0.26) / 0.27)) / bright,
                                   warmth * mix(0.45, 1.0, relight));   // still calms shine when not relighting

    float warmEdge = m * clamp(1.0 - leftOf.r, 0.0, 1.0);
    float coolEdge = m * clamp(1.0 - rightOf.r, 0.0, 1.0);
    float body = 0.030 + dot(skin, float3(0.2126, 0.7152, 0.0722)) * 0.9;
    // in the warm set the second edge light is copper too, not blue-grey
    float3 second = useSet > 0.5 ? mix(warm, float3(0.85, 0.62, 0.46), 0.6) : cool + 0.22;
    skin += (toLinear(warm) * warmEdge * 1.00 + toLinear(second) * coolEdge * 0.30) * rim * body * 2.2 * (1.0 - 0.6 * chest);

    return float4(toCode(mix(lit, skin, m)), 1.0);
}

// Puts the speaker under the room's light: bounce colour in the shadows and the clothes, less
// light low down, a soft edge from the window on one side and the lamp on the other, and a little
// of the room wrapping round the outline. Only colour and level change; nothing is redrawn.
static float3 hue(float3 c) { return c / max(dot(c, float3(0.2126, 0.7152, 0.0722)), 0.001); }
[[ stitchable ]] float4 roomLight(coreimage::sample_t image, coreimage::sample_t matte, coreimage::sample_t fromLeft,
                                  coreimage::sample_t fromRight, coreimage::sample_t body, coreimage::sample_t spill,
                                  float2 face, float faceSize, float3 ambient, float3 leftColour, float3 rightColour,
                                  float amount, coreimage::destination dest) {
    float m = clamp(matte.r, 0.0, 1.0);
    if (m < 0.002 || amount <= 0.0) return image;
    float2 p = dest.coord();
    float3 c = toLinear(image.rgb);
    float3 was = c;
    float luma = dot(c, float3(0.2126, 0.7152, 0.0722));
    float high = max(image.r, max(image.g, image.b)), low = min(image.r, min(image.g, image.b));
    float pale = (1.0 - smoothstep(0.10, 0.32, (high - low) / max(high, 0.001))) * smoothstep(0.25, 0.55, high);
    float onFace = blob(p, face, float2(faceSize * 0.78, faceSize * 0.95));
    float3 air = hue(toLinear(ambient));
    float3 l = hue(toLinear(leftColour)), r = hue(toLinear(rightColour));

    // bounce light: strongest in the shadows and on pale cloth, gentlest on the lit face
    float shadow = 1.0 - smoothstep(0.02, 0.42, luma);
    float tint = mix(0.26, 0.52, shadow);
    tint = mix(tint, 0.52, pale);
    tint *= 1.0 - 0.42 * onFace;
    c *= mix(float3(1.0), air, tint * amount);

    // each side takes the colour of the light on that side
    float across = (p.x - face.x) / faceSize;
    float onLeft = smoothstep(0.0, 1.1, -across), onRight = smoothstep(0.0, 1.1, across);
    c *= mix(float3(1.0), l, 0.34 * onLeft * amount);
    c *= mix(float3(1.0), r, 0.30 * onRight * amount);

    // a room this dim cannot light the clothes as brightly as the face
    float lower = smoothstep(face.y - faceSize * 0.55, face.y - faceSize * 1.9, p.y);
    c *= 1.0 - amount * (0.08 + 0.30 * lower + 0.10 * max(onLeft, onRight));
    c *= 1.0 - amount * 0.20 * pale * smoothstep(0.35, 0.85, luma);
    c = mix(c, c * c * (3.0 - 2.0 * min(c, 1.0)), 0.10 * amount * (1.0 - onFace));

    // edge light, and the room wrapping round the outline
    float leftEdge = clamp(m - fromLeft.r, 0.0, 1.0), rightEdge = clamp(m - fromRight.r, 0.0, 1.0);
    float catching = 0.020 + 0.50 * dot(was, float3(0.2126, 0.7152, 0.0722));
    c += amount * catching * (l * leftEdge * 0.45 + r * rightEdge * 0.45) * (1.0 - 0.45 * lower);
    float wrap = clamp((1.0 - body.r) * 1.4, 0.0, 1.0);
    float3 room = min(toLinear(spill.rgb), float3(0.20));
    c = mix(c, 1.0 - (1.0 - c) * (1.0 - room), wrap * 0.16 * amount * lower);

    return float4(mix(image.rgb, toCode(c), m), 1.0);
}

// Filmic finish in display space: deeper toe, soft shoulder (keeps pale clothing from clipping).
static float curve(float x) {
    x = clamp(x, 0.0, 1.0);
    x = mix(x, x * x * (3.0 - 2.0 * x), 0.08);
    x = max(x - 0.010, 0.0) / 0.990;
    return x > 0.76 ? 0.76 + 0.19 * tanh((x - 0.76) / 0.20) : x;
}

[[ stitchable ]] float4 finish(coreimage::sample_t image, coreimage::sample_t glow, float bloom, float grain,
                               float seed, coreimage::destination dest) {
    float3 c = image.rgb;
    float3 g = max(glow.rgb - 0.62, 0.0);
    c = 1.0 - (1.0 - c) * (1.0 - clamp(g * bloom * 3.0, 0.0, 1.0));
    c = float3(curve(c.r), curve(c.g), curve(c.b));
    float luma = dot(c, float3(0.2126, 0.7152, 0.0722));
    float shade = (1.0 - luma) * (1.0 - luma);
    c += float3(-0.006, 0.001, 0.010) * shade * smoothstep(0.0, 0.12, luma);
    c = mix(float3(luma), c, 0.99);
    float2 p = floor(dest.coord()) + seed * float2(17.0, 59.0);
    float noise = fract(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453);
    c += (noise - 0.5) * grain / 255.0 * 2.0;
    return float4(clamp(c, 0.0, 1.0), 1.0);
}
"""

let args = CommandLine.arguments
guard args.count == 3 || (args.count == 6 && args[3] == "--stills") else {
    fail("usage: studio <face.mp4> <settings.json> [--stills n,n,n <dir>]")
}
let settings: Settings
do { settings = try JSONDecoder().decode(Settings.self, from: Data(contentsOf: URL(fileURLWithPath: args[2]))) }
catch { fail("bad studio settings: \(error)") }
let stills: Set<Int> = args.count > 3 ? Set(args[4].split(separator: ",").compactMap { Int($0) }) : []
let stillsDir = args.count > 3 ? args[5] : ""

let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
let track = try await asset.loadTracks(withMediaType: .video)[0]
let size = try await track.load(.naturalSize)
let width = Int(size.width), height = Int(size.height), pixels = width * height
let frame = CGRect(x: 0, y: 0, width: width, height: height)
let reader = try AVAssetReader(asset: asset)
let output = AVAssetReaderTrackOutput(track: track, outputSettings:
    [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
reader.add(output)
reader.startReading()

// The outline is read frame for frame alongside the footage. It is either one finished video, or a
// list of parts that rvm_matte.py is still adding to: then wait for each part as it is needed.
var matteReader: AVAssetReader? = nil
var matteOutput: AVAssetReaderTrackOutput? = nil
let inParts = settings.matte.hasSuffix(".csv")
var partsOpened = 0
func openOutline(_ url: URL) async throws {
    let outline = AVURLAsset(url: url)
    let outlineTrack = try await outline.loadTracks(withMediaType: .video)[0]
    let outlineSize = try await outlineTrack.load(.naturalSize)
    guard outlineSize == size else { fail("the outline video is \(outlineSize), the footage is \(size)") }
    let r = try AVAssetReader(asset: outline)
    let o = AVAssetReaderTrackOutput(track: outlineTrack, outputSettings:
        [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
    r.add(o)
    r.startReading()
    matteReader = r
    matteOutput = o
}
func openNextPart() async throws -> Bool {
    let list = URL(fileURLWithPath: settings.matte)
    let ended = list.appendingPathExtension("done")       // written once no more parts will come
    var waited = 0.0
    while true {
        let finished = FileManager.default.fileExists(atPath: ended.path)    // look before reading the list
        let text = (try? String(contentsOf: list, encoding: .utf8)) ?? ""
        let lines = text.components(separatedBy: "\n").dropLast()           // only whole lines
        if partsOpened < lines.count {
            let name = String(lines[lines.startIndex + partsOpened].split(separator: ",")[0])
            try await openOutline(list.deletingLastPathComponent().appendingPathComponent(name))
            partsOpened += 1
            return true
        }
        if finished { return false }
        if waited > 900 { fail("no new outline for 15 minutes: has the cut-out stopped?") }
        try await Task.sleep(nanoseconds: 300_000_000)
        waited += 0.3
    }
}
func nextOutline() async throws -> CMSampleBuffer? {
    while true {
        if let sample = matteOutput?.copyNextSampleBuffer() { return sample }
        if let r = matteReader, r.status == .failed { fail("cannot read the outline: \(String(describing: r.error))") }
        if !inParts { return nil }
        if try await !openNextPart() { return nil }
    }
}
if !settings.matte.isEmpty && !inParts { try await openOutline(URL(fileURLWithPath: settings.matte)) }
let given = !settings.matte.isEmpty
let gateReach = 14.0     // px the video outline may reach past the per-frame mask
let bodyMargin = 22.0    // px around the video outline's solid body where it alone decides the edge
let deepInside = 9.0     // px inside the per-frame mask that are always the speaker

let kernels = try CIKernel.kernels(withMetalString: metal)
func colour(_ name: String) -> CIColorKernel {
    guard let k = kernels.first(where: { $0.name == name }) as? CIColorKernel else { fail("missing kernel \(name)") }
    return k
}
let plate = colour("plate"), light = colour("light"), finish = colour("finish")
let skinWeight = colour("skinWeight"), weighted = colour("weighted"), retouch = colour("retouch")
let goldGrade = colour("goldGrade")
let roomLight = colour("roomLight")
guard let bilateral = kernels.first(where: { $0.name == "bilateral" }) else { fail("missing kernel bilateral") }

// No colour management: the kernels work on the video's own code values, so nothing shifts on the way through.
let context = CIContext(options: [.workingColorSpace: NSNull(), .workingFormat: CIFormat.RGBAh])
let segment = VNGeneratePersonSegmentationRequest()
segment.qualityLevel = .accurate
segment.outputPixelFormat = kCVPixelFormatType_OneComponent8
let faces = VNDetectFaceLandmarksRequest()

// Features that must stay crisp, painted black on a white sheet from the face landmarks.
let sheet = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width,
                      space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue)!
sheet.setFillColor(gray: 1, alpha: 1)
sheet.fill(frame)
func paintFeatures(_ face: VNFaceObservation) {
    guard let marks = face.landmarks else { return }
    let side = max(face.boundingBox.width * size.width, face.boundingBox.height * size.height)
    sheet.setFillColor(gray: 1, alpha: 1)
    sheet.fill(frame)
    sheet.setFillColor(gray: 0, alpha: 1)
    sheet.setStrokeColor(gray: 0, alpha: 1)
    sheet.setLineJoin(.round)
    sheet.setLineCap(.round)
    let parts: [(VNFaceLandmarkRegion2D?, Double)] = [(marks.leftEye, 0.040), (marks.rightEye, 0.040),
        (marks.leftEyebrow, 0.040), (marks.rightEyebrow, 0.040), (marks.outerLips, 0.022)]
    for (region, grow) in parts {
        guard let points = region?.pointsInImage(imageSize: size), points.count > 2 else { continue }
        sheet.beginPath()
        sheet.addLines(between: points)
        sheet.closePath()
        sheet.setLineWidth(side * grow)
        sheet.drawPath(using: .fillStroke)
    }
}

func blurred(_ image: CIImage, _ radius: Double) -> CIImage {
    image.clampedToExtent().applyingGaussianBlur(sigma: radius).cropped(to: frame)
}
func morph(_ image: CIImage, _ filter: String, _ radius: Double) -> CIImage {
    image.clampedToExtent().applyingFilter(filter, parameters: [kCIInputRadiusKey: radius]).cropped(to: frame)
}

var maskBytes = [UInt8](repeating: 0, count: pixels * 4)
var alpha = [UInt8](repeating: 0, count: pixels)
var previous = [Float](repeating: 0, count: pixels)
var rendered = [UInt8](repeating: 0, count: pixels * 4)
var faceCentre = CGPoint(x: Double(width) / 2, y: Double(height) * 0.55)
var faceSize = Double(width) * 0.36
var haveFace = false
var count = 0, empty = 0

// fill the frame, keeping the picture's shape, centred
func filling(_ picture: CIImage) -> CIImage {
    let scale = max(size.width / picture.extent.width, size.height / picture.extent.height)
    let fitted = picture.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
    return fitted.transformed(by: CGAffineTransform(translationX: (size.width - fitted.extent.width) / 2 - fitted.extent.minX,
                                                    y: (size.height - fitted.extent.height) / 2 - fitted.extent.minY))
        .cropped(to: frame)
}

// A backdrop that is a video moves: it is read frame for frame and starts again when it ends.
let moving = ["mp4", "mov"].contains((settings.backdrop as NSString).pathExtension.lowercased())
var loopTrack: AVAssetTrack? = nil
var loopReader: AVAssetReader? = nil
var loopOutput: AVAssetReaderTrackOutput? = nil
let loopAsset = AVURLAsset(url: URL(fileURLWithPath: settings.backdrop))
if moving { loopTrack = try await loopAsset.loadTracks(withMediaType: .video).first }
func nextLoopFrame() -> CVPixelBuffer {
    for _ in 0..<2 {
        if let o = loopOutput, let s = o.copyNextSampleBuffer(), let b = CMSampleBufferGetImageBuffer(s) { return b }
        guard let t = loopTrack, let r = try? AVAssetReader(asset: loopAsset) else { break }
        let o = AVAssetReaderTrackOutput(track: t, outputSettings:
            [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        r.add(o)
        r.startReading()
        loopReader = r
        loopOutput = o
    }
    fail("cannot read the backdrop \(settings.backdrop)")
}

var backdrop = CIImage(color: CIColor.black).cropped(to: frame)
if !settings.backdrop.isEmpty && !moving {
    guard let picture = CIImage(contentsOf: URL(fileURLWithPath: settings.backdrop), options: [.colorSpace: NSNull()])
    else { fail("cannot read the backdrop \(settings.backdrop)") }
    backdrop = filling(picture)
}

while let sample = output.copyNextSampleBuffer() {
    defer { count += 1 }
    var outlineSample: CMSampleBuffer? = nil
    if given {                 // read even for skipped frames, so the two stay in step
        outlineSample = try await nextOutline()
        if outlineSample == nil { fail("the outline video ends before the footage, at frame \(count)") }
    }
    var loopFrame: CVPixelBuffer? = nil
    if moving { loopFrame = nextLoopFrame() }     // read even for skipped frames, so time stays right
    if !stills.isEmpty && !stills.contains(count) {
        if count > stills.max()! { break }
        continue
    }
    try autoreleasepool {
        guard let buffer = CMSampleBufferGetImageBuffer(sample) else { return }
        try VNImageRequestHandler(cvPixelBuffer: buffer, options: [:]).perform([segment, faces])
        guard let result = segment.results?.first else { fail("no segmentation at frame \(count)") }

        // follow the face so the lights move with the speaker; jump straight there after a cut
        if let face = faces.results?.max(by: { $0.boundingBox.width < $1.boundingBox.width }) {
            paintFeatures(face)
            let box = face.boundingBox
            let centre = CGPoint(x: box.midX * size.width, y: box.midY * size.height)
            let side = max(box.width * size.width, box.height * size.height)
            let jumped = hypot(centre.x - faceCentre.x, centre.y - faceCentre.y) > size.width * 0.12
            let follow = (!haveFace || jumped || !stills.isEmpty) ? 1.0 : 0.10
            faceCentre = CGPoint(x: faceCentre.x + (centre.x - faceCentre.x) * follow,
                                 y: faceCentre.y + (centre.y - faceCentre.y) * follow)
            faceSize += (side - faceSize) * follow
            haveFace = true
        }

        let image = CIImage(cvPixelBuffer: buffer)
        if let b = loopFrame { backdrop = filling(CIImage(cvPixelBuffer: b, options: [.colorSpace: NSNull()])) }
        func sized(_ picture: CIImage) -> CIImage {
            picture.transformed(by: CGAffineTransform(scaleX: size.width / picture.extent.width,
                                                      y: size.height / picture.extent.height)).cropped(to: frame)
        }
        var raw = sized(CIImage(cvPixelBuffer: result.pixelBuffer))
        if given {
            guard let s = outlineSample, let b = CMSampleBufferGetImageBuffer(s) else { fail("bad outline frame \(count)") }
            // The video outline holds edges through motion but can invent patches of wall well away
            // from the speaker. It only counts near where Apple's per-frame mask also sees a person.
            let near = morph(raw, "CIMorphologyMaximum", gateReach)
                .applyingFilter("CIColorMatrix", parameters: ["inputRVector": CIVector(x: 2, y: 0, z: 0, w: 0),
                    "inputGVector": CIVector(x: 0, y: 2, z: 0, w: 0), "inputBVector": CIVector(x: 0, y: 0, z: 2, w: 0)])
                .applyingFilter("CIColorClamp").cropped(to: frame)
            let video = sized(CIImage(cvPixelBuffer: b))
            let gated = !settings.gate ? video
                : video.applyingFilter("CIMinimumCompositing", parameters: [kCIInputBackgroundImageKey: blurred(near, 4.0)])
                    .cropped(to: frame)
            // It is also poor at a hand that the edge of the picture cuts off from the body: it
            // comes out in ragged pieces where the per-frame mask has it whole. So away from what
            // the video outline is sure about, the per-frame mask fills in.
            let sure = video.applyingFilter("CIColorMatrix", parameters: ["inputRVector": CIVector(x: 5, y: 0, z: 0, w: 0),
                    "inputGVector": CIVector(x: 0, y: 5, z: 0, w: 0), "inputBVector": CIVector(x: 0, y: 0, z: 5, w: 0),
                    "inputBiasVector": CIVector(x: -3.5, y: -3.5, z: -3.5, w: 0)])
                .applyingFilter("CIColorClamp").cropped(to: frame)
            // drop small solid crumbs first, then allow a margin around what is left
            let body = morph(morph(sure, "CIMorphologyMinimum", 8.0), "CIMorphologyMaximum", 8.0 + bodyMargin)
            let away = blurred(body, 6.0).applyingFilter("CIColorInvert").cropped(to: frame)
            let fill = raw.applyingFilter("CIMinimumCompositing", parameters: [kCIInputBackgroundImageKey: away])
            // Well inside the per-frame mask is the speaker for certain: this closes the cracks that
            // open between the two outlines in a fast, blurred hand.
            let deep = morph(raw, "CIMorphologyMinimum", deepInside)
            raw = gated.applyingFilter("CIMaximumCompositing", parameters: [kCIInputBackgroundImageKey: fill])
                .applyingFilter("CIMaximumCompositing", parameters: [kCIInputBackgroundImageKey: deep])
                .cropped(to: frame)
        }
        // steady the edge between frames; a big change is real movement or a cut
        context.render(raw, toBitmap: &maskBytes, rowBytes: width * 4, bounds: frame, format: .BGRA8, colorSpace: nil)
        for i in 0..<pixels {
            var v = Float(maskBytes[i * 4 + 2]) / 255
            // a made outline already carries its own memory; Apple's per-frame mask needs steadying
            if !given && count > 0 && stills.isEmpty && abs(v - previous[i]) < 0.35 { v = 0.7 * v + 0.3 * previous[i] }
            previous[i] = v
            // tighten the made outline's soft haze, but keep enough softness for motion blur
            let t = min(1, max(0, given ? (v - 0.18) / 0.68 : (v - 0.25) / 0.5))
            alpha[i] = UInt8((t * t * (3 - 2 * t) * 255).rounded())
        }
        let steady = CIImage(bitmapData: Data(alpha), bytesPerRow: width, size: size, format: .L8, colorSpace: nil)
        let matte = blurred(morph(steady, "CIMorphologyMinimum", given ? 1.0 : 2.0), given ? 0.6 : 1.0)

        // room plate: cut a slightly generous hole, then blur what is left
        let hole = blurred(morph(steady, "CIMorphologyMaximum", 5.0), 2.0)
        let room = plate.apply(extent: frame, arguments: [image, hole])!
        let soft = room.clampedToExtent().applyingFilter("CIDiscBlur", parameters: [kCIInputRadiusKey: settings.blur])
            .cropped(to: frame)
        let wide = blurred(room, 48)

        // speaker: gentle denoise everywhere; local contrast and detail only well inside the outline
        // (sharpening across the edge would draw a bright halo)
        let clean = image.clampedToExtent()
            .applyingFilter("CINoiseReduction", parameters: ["inputNoiseLevel": 0.016, "inputSharpness": 0.25])
            .cropped(to: frame)
        let crisp = clean.clampedToExtent()
            .applyingFilter("CIUnsharpMask", parameters: [kCIInputRadiusKey: 22.0, kCIInputIntensityKey: 0.09])
            .applyingFilter("CISharpenLuminance", parameters: [kCIInputSharpnessKey: 0.20, kCIInputRadiusKey: 1.6])
            .cropped(to: frame)
        let interior = blurred(morph(steady, "CIMorphologyMinimum", 9.0), 3.0)
        let detailed = crisp.applyingFilter("CIBlendWithMask", parameters: [
            kCIInputBackgroundImageKey: clean, kCIInputMaskImageKey: interior]).cropped(to: frame)

        // skin retouch
        let features = CIImage(bitmapData: Data(bytes: sheet.data!, count: pixels), bytesPerRow: width,
                               size: size, format: .L8, colorSpace: nil)
        let allow = blurred(morph(features, "CIMorphologyMinimum", 2.0), 3.5)
            .applyingFilter("CIMultiplyCompositing", parameters: [
                kCIInputBackgroundImageKey: blurred(morph(steady, "CIMorphologyMinimum", 3.0), 2.0)])
            .cropped(to: frame)
        let weight = blurred(skinWeight.apply(extent: frame, arguments: [blurred(clean, 3.0), allow])!, 2.0)
        let source = blurred(clean, 1.0).clampedToExtent()
        let smooth = bilateral.apply(extent: frame, roiCallback: { _, r in r.insetBy(dx: -15, dy: -15) },
                                     arguments: [source, blurred(clean, 4.5).clampedToExtent(), 13.0, 0.095])!
        let tone = blurred(weighted.apply(extent: frame, arguments: [smooth, weight])!, 13.0)
        let person = retouch.apply(extent: frame, arguments: [
            detailed, image, smooth, blurred(image, 1.7), tone, weight, settings.skin])!
        if !stills.isEmpty && ProcessInfo.processInfo.environment["STUDIO_SKIN_MASK"] != nil {
            let url = URL(fileURLWithPath: stillsDir).appendingPathComponent("skin_\(count).png")
            try context.writePNGRepresentation(of: weight, to: url, format: .RGBA8,
                                               colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!)
        }
        let core = blurred(morph(steady, "CIMorphologyMinimum", 5.0), 1.5)
        let outside = core.applyingFilter("CIColorInvert").cropped(to: frame)
        let inner = blurred(plate.apply(extent: frame, arguments: [clean, outside])!, 5.0)

        let around = blurred(steady, 5.0)
        let leftOf = around.clampedToExtent().transformed(by: CGAffineTransform(translationX: 13, y: -4)).cropped(to: frame)
        let rightOf = around.clampedToExtent().transformed(by: CGAffineTransform(translationX: -13, y: -4)).cropped(to: frame)

        let lit = light.apply(extent: frame, arguments: [
            soft, wide, person, matte, inner, core, leftOf, rightOf, backdrop,
            settings.backdrop.isEmpty ? 0.0 : 1.0,
            CIVector(x: size.width, y: size.height), CIVector(x: faceCentre.x, y: faceCentre.y), faceSize,
            settings.wall, settings.pool,
            CIVector(x: settings.warm[0], y: settings.warm[1], z: settings.warm[2]),
            CIVector(x: settings.cool[0], y: settings.cool[1], z: settings.cool[2]),
            settings.practical, settings.key, settings.rim, settings.relight])!
        let graded = goldGrade.apply(extent: frame, arguments: [lit, settings.gold, settings.selective])!
        var placed = graded
        if settings.match > 0 {
            func rgb(_ v: [Double]) -> CIVector { CIVector(x: v[0], y: v[1], z: v[2]) }
            let edge = blurred(steady, 9.0).clampedToExtent()
            let fromLeft = edge.transformed(by: CGAffineTransform(translationX: 22, y: -7)).cropped(to: frame)
            let fromRight = edge.transformed(by: CGAffineTransform(translationX: -22, y: -7)).cropped(to: frame)
            placed = roomLight.apply(extent: frame, arguments: [
                graded, matte, fromLeft, fromRight, blurred(steady, 16.0),
                blurred(settings.backdrop.isEmpty ? image : backdrop, 44),
                CIVector(x: faceCentre.x, y: faceCentre.y), faceSize, rgb(settings.ambient),
                rgb(settings.windowRight ? settings.lampLight : settings.windowLight),
                rgb(settings.windowRight ? settings.windowLight : settings.lampLight), settings.match])!
        }
        let final = finish.apply(extent: frame, arguments: [
            placed, blurred(placed, 20), settings.bloom, settings.grain, Double(count % 97)])!

        context.render(final, toBitmap: &rendered, rowBytes: width * 4, bounds: frame, format: .BGRA8, colorSpace: nil)
        context.render(matte, toBitmap: &maskBytes, rowBytes: width * 4, bounds: frame, format: .BGRA8, colorSpace: nil)
        var solid = 0
        for i in 0..<pixels {
            rendered[i * 4 + 3] = maskBytes[i * 4 + 2]
            if i < pixels / 3 && maskBytes[i * 4 + 2] > 127 { solid += 1 }
        }
        if solid == 0 { empty += 1 }
        if stills.isEmpty {
            rendered.withUnsafeBytes { FileHandle.standardOutput.write(Data($0)) }
        } else {
            let info = CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue)
            let cg = CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: width * 4,
                             space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: info,
                             provider: CGDataProvider(data: Data(rendered) as CFData)!, decode: nil,
                             shouldInterpolate: false, intent: .defaultIntent)!
            let url = URL(fileURLWithPath: stillsDir).appendingPathComponent("studio_\(count).png")
            let out = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)!
            CGImageDestinationAddImage(out, cg, nil)
            if !CGImageDestinationFinalize(out) { fail("could not write \(url.path)") }
        }
    }
    if stills.isEmpty && count % 600 == 599 { FileHandle.standardError.write("studio \(count + 1) frames\n".data(using: .utf8)!) }
}
withExtendedLifetime(reader) {}
if stills.isEmpty {
    guard reader.status == .completed else { fail("read failed: \(String(describing: reader.error))") }
}
FileHandle.standardError.write("studio done: \(stills.isEmpty ? count : stills.count) frames, \(empty) with nobody in the top third\n".data(using: .utf8)!)
