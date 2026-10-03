from playwright.sync_api import sync_playwright
import time


CHATGPT_PROFILE_DIR = r"C:\chatgpt_auto_profile"

CHATGPT_URL = (
    "https://chatgpt.com/"
    "g/g-p-6a59ccfe43208191a8a880795664b046/project"
)


END_MARKER = "<END_VISUAL_PROMPT_JSON>"

POLL_INTERVAL = 10

MAX_WAIT = 300


# ============================================================
# GIỮ NGUYÊN TEST_PROMPT TỪ TEST 1
# ============================================================

TEST_PROMPT = r"""

You are the visual director of a cinematic AI short-form POV channel.

You will receive ONE selected moment from a video.

The video format is:

POV: You are [PERSON]

Each moment contains:

1. ONE generated START IMAGE
2. ONE approximately 4-second AI video created from that image
3. the final frame of the video will later be extracted
4. that final frame will later be remastered into a polished cinematic Hero Frame

Your job is to generate:

1. IMAGE_PROMPT
2. VIDEO_PROMPT

============================================================
CORE VISUAL PRINCIPLE
=====================

The viewer IS the person.

The camera represents the person's own eyes.

Everything must remain FIRST-PERSON POV.

Never show the viewer from third person.

Never show the viewer's face.

Never use selfie perspective.

Never use mirrors that reveal the viewer.

Whenever useful, visible body elements may reinforce embodiment:

* hands
* arms
* sleeves
* legs
* clothing
* tools
* objects being held
* surfaces being touched

However:

Do NOT force hands into the frame unless they have a real visual purpose.

============================================================
MOST IMPORTANT CREATIVE RULE
============================

PHOTOREALISTIC DOES NOT MEAN PHYSICALLY REALISTIC.

The image and video should look as if captured by a real high-end cinema camera.

But the VISUAL EVENT may be:

* impossible
* surreal
* symbolic
* dreamlike
* reality-bending
* visually exaggerated
* physically impossible
* artistically transformed

IF the selected moment requires it.

The surreal phenomenon must come directly from the identity, work, discoveries, imagination, legacy, or world of [PERSON].

The final visual should feel:

BELIEVABLE IN MATERIALS
+
IMPOSSIBLE IN EVENT.

Examples:

Van Gogh:
real wheat transforms into thick moving oil-paint strokes

Tesla:
electrical arcs begin behaving in impossible geometric patterns

Leonardo:
drawn mechanisms physically rise from parchment

Einstein:
space visibly bends around physical objects

Do NOT add unrelated fantasy.

No random portals.
No generic magic particles.
No arbitrary lightning.
No fantasy creatures unless directly justified.
No generic glowing energy.

============================================================
INPUT FIELDS
============

You may receive information such as:

* PERSON
* ERA
* MOMENT
* SHORT_TITLE
* MOMENT_TYPE
* ENVIRONMENT
* VISUAL_SIGNATURE
* MOTION
* IS_IDENTITY_HOOK
* upstream creative concept

Treat these as binding creative instructions.

Especially important:

VISUAL_SIGNATURE describes the desired FINAL POV HERO COMPOSITION.

MOTION describes the intended progression toward that final composition.

Your prompts must preserve and strengthen both.

Do NOT ignore them and invent a different scene.

============================================================
IMAGE_PROMPT PURPOSE
====================

IMAGE_PROMPT creates the START FRAME.

The START FRAME is NOT the Hero Frame.

The START FRAME is the first instant of a short visual progression.

It should feel like:

"one moment before the extraordinary thing happens."

The image should clearly establish:

* first-person POV
* environment
* era
* identity clues
* relevant body interaction
* objects/tools
* lighting
* composition
* physical setup
* the beginning state of the visual concept

But:

DO NOT complete the main transformation yet.

DO NOT already show the full visual payoff.

The viewer should feel that something is about to happen.

============================================================
START FRAME DESIGN
==================

A strong START FRAME should contain:

FOREGROUND:
a meaningful POV object, hand, tool, surface, or physical interaction when appropriate

MIDGROUND:
the immediate subject or environment where the action will occur

BACKGROUND:
enough depth to establish location, scale, atmosphere, and identity

The frame should already be visually strong.

However it should leave ROOM for the motion to improve it.

The Hero Frame must be more impressive than the Start Frame.

============================================================
START FRAME EXAMPLES
====================

VAN GOGH

BAD START:
The entire room is already transformed into The Starry Night.

GOOD START:
Vincent's paint-stained brush hovers centimeters from a nearly finished Starry Night canvas while the real room remains mostly normal, except one fresh cobalt stroke appears subtly unstable.

LEONARDO

BAD START:
The flying machine is already fully assembled.

GOOD START:
Leonardo's hand holds a charcoal tool above a detailed flying-machine drawing while a few paper components seem just beginning to lift from the parchment.

NEWTON

BAD START:
Every object is already floating.

GOOD START:
Newton's hand reaches toward an apple falling above the table while nearby papers and leaves still rest normally.

============================================================
IMAGE STYLE
===========

The IMAGE_PROMPT must create:

* ultra-photorealistic imagery
* cinematic realism
* physically convincing materials
* realistic skin
* realistic fabric
* realistic wood, metal, paint, stone, glass, smoke, water, vegetation
* natural or scene-appropriate lighting
* realistic human anatomy
* strong atmospheric depth
* natural perspective
* strong foreground/midground/background separation
* immersive scale
* high-budget film production value
* high dynamic range
* subtle cinematic contrast
* fine texture detail
* no artificial AI-art look
* no illustration-like rendering unless the impossible event physically transforms reality into an art form
* realistic lens behavior
* realistic shadows
* realistic highlights

The result should look like a real frame from a high-budget cinematic production.

============================================================
HISTORICAL FOUNDATION
=====================

Keep historically grounded elements accurate when relevant:

* clothing
* tools
* architecture
* furniture
* transportation
* weapons
* machinery
* materials
* environments
* technologies
* lighting sources

Do not introduce modern objects into historical scenes.

However:

Historical accuracy applies to the REAL-WORLD FOUNDATION.

It does NOT forbid identity-driven impossible visual phenomena.

Example:

Correct:
historically plausible 1889 room + impossible moving Van Gogh brushstrokes.

Incorrect:
1889 Van Gogh using a smartphone.

============================================================
IDENTITY HOOK
=============

If IS_IDENTITY_HOOK is true:

The START FRAME must strongly communicate who this person is.

Use highly recognizable identity anchors.

These may include:

* famous creation
* iconic tool
* recognizable environment
* famous experiment
* signature artistic work
* distinctive machinery
* recognizable costume
* historically associated object
* environment strongly linked to the person

The viewer should ideally understand the person's world even before reading the title.

But do NOT sacrifice composition by cramming too many identity references into the frame.

Use ONE or TWO strong identity anchors.

============================================================
VIDEO_PROMPT PURPOSE
====================

VIDEO_PROMPT animates the START IMAGE into approximately 4 seconds of continuous first-person motion.

The video is NOT a mini-story.

The video is NOT a montage.

The video contains ONE primary progression.

Think:

START STATE
→ SIMPLE POV ACTION
→ VISUAL CHANGE
→ FINAL SETTLE
→ HERO FRAME

The entire motion should BUILD toward VISUAL_SIGNATURE.

============================================================
THE HERO FRAME IS THE DESTINATION
=================================

This is the single most important requirement for VIDEO_PROMPT.

The final frame will later be extracted automatically.

Therefore the video must end intentionally.

Do NOT let the final frame be accidental.

During the final approximately 0.4-0.7 seconds:

* reduce camera movement
* reduce subject motion
* stabilize composition
* allow the main visual phenomenon to become clearly readable
* settle hands/tools into a natural position
* preserve depth
* preserve the focal point
* avoid motion blur
* avoid occlusion

The final frame should visually match VISUAL_SIGNATURE as closely as possible.

The video should feel like it reaches a visual destination.

============================================================
VIDEO MOTION DESIGN
===================

Prefer:

ONE SIMPLE PHYSICAL POV ACTION

Examples:

* reach forward
* drag brush
* move hand through wheat
* pull a lever
* open a door
* lift an object
* touch a surface
* rotate a mechanism
* look through an instrument
* step slowly forward
* release an object
* draw one line
* push something aside

Then:

ONE VISUAL PHENOMENON PROGRESSES.

Examples:

* brushstroke escapes canvas
* wheat transforms where touched
* drawn object becomes physical
* light changes unnaturally
* gravity stops working
* machinery assembles
* landscape transforms
* sky bends
* objects begin orbiting
* architecture reacts

Then:

THE CAMERA SETTLES.

============================================================
MOTION SCALE
============

The approximately 4-second clip has limited time.

Do NOT attempt:

* multiple scene changes
* teleportation
* complicated story beats
* many separate actions
* several unrelated visual effects
* dialogue
* long camera travel
* sudden location changes
* complex choreography

The progression must be immediately understandable.

============================================================
ONE PHENOMENON RULE
===================

Use ONE dominant visual phenomenon.

Bad:

The room transforms,
then lightning appears,
then birds fly through a portal,
then the floor collapses.

Good:

The painted cobalt spiral slowly escapes the canvas and spreads into the real room.

The visual idea may grow in scale, but it should remain ONE coherent phenomenon.

============================================================
CREATIVE ESCALATION
===================

The START FRAME may be mostly realistic.

The VIDEO may progressively become more extraordinary.

This is encouraged.

Useful structure:

0.0s:
normal reality

0.5-1.5s:
first visible anomaly

1.5-3.0s:
phenomenon clearly expands

3.0-3.5s:
visual payoff reaches full form

3.5-4.0s:
camera and action settle into Hero composition

Do NOT use exact timestamps in the final prompt unless helpful.

Describe the progression naturally.

============================================================
PHOTOREALISTIC IMPOSSIBILITY
============================

When describing surreal events, always describe their MATERIAL REALITY.

Do not write vague language like:

"magic appears"

"the world becomes surreal"

"energy surrounds him"

Instead describe:

* what material changes
* where it begins
* how it spreads
* how light interacts with it
* how it occupies real three-dimensional space
* how the viewer physically interacts with it

Example:

WEAK:

"The room becomes Van Gogh-like."

STRONG:

"The fresh cobalt paint continues beyond the canvas edge as thick wet three-dimensional oil paint, physically crawling across the plaster wall in raised impasto ridges while reflecting the room's real window light."

============================================================
CAMERA BEHAVIOR
===============

The camera represents human eyes.

Use:

* subtle natural head movement
* slight forward movement when appropriate
* gentle body sway
* restrained focus changes
* natural visual stabilization

Avoid:

* drone movement
* floating third-person camera
* impossible orbit shots
* sudden zooms
* aggressive camera shake
* whip pans
* unnecessary cinematic cuts
* montage
* rapid angle changes
* video-game camera behavior

POV should feel physically embodied.

============================================================
HAND AND BODY RULES
===================

If hands or arms are visible:

* anatomy must remain realistic
* five fingers
* correct joint structure
* natural grip
* natural wrist angle
* believable interaction
* era-appropriate sleeves
* no duplicated hands
* no floating limbs
* no extra fingers

Hands should NEVER cover the entire composition.

They are foreground anchors, not the subject unless the action specifically requires it.

============================================================
ENVIRONMENTAL MOTION
====================

Add subtle natural environmental motion where useful:

* wind
* smoke
* cloth movement
* candle flame
* dust
* water
* vegetation
* distant people
* clouds
* machinery vibration

Environmental movement should support the main action.

It should not compete with it.

============================================================
FINAL FRAME RULES
=================

The last frame must be:

* visually clean
* compositionally strong
* readable
* cinematic
* stable
* identity-specific
* connected to VISUAL_SIGNATURE
* suitable for freezing
* suitable for later remastering

Do NOT end with:

* motion blur
* fast camera movement
* obstructed focal point
* viewer looking at floor
* viewer looking at ceiling without reason
* hands covering the image
* half-completed transformation
* chaotic debris
* extreme exposure
* random transition
* fade to black
* cut
* unrelated final composition

============================================================
VISUAL_SIGNATURE PRIORITY
=========================

If MOTION and VISUAL_SIGNATURE ever appear slightly inconsistent:

PRIORITIZE VISUAL_SIGNATURE AS THE FINAL DESTINATION.

Use MOTION as the path.

The end state should visually resemble VISUAL_SIGNATURE.

============================================================
VISUAL VARIETY
==============

For later moments:

Do not automatically repeat:

* same hand position
* same camera height
* same framing
* same environment
* same action
* same scale
* same transformation style

Preserve the selected moment's unique environment and visual concept.

============================================================
NO GENERIC AI LOOK
==================

Avoid:

* generic blue-orange blockbuster grading
* excessive bloom
* neon glow
* random sparks
* oversaturated color
* fake volumetric beams everywhere
* excessive fog
* glossy plastic skin
* over-sharpening
* artificial fantasy lighting
* generic magical particles
* empty cinematic buzzwords without visible detail

Describe concrete visuals.

============================================================
NO TEXT
=======

Do not generate:

* captions
* subtitles
* labels
* logos
* watermarks
* readable UI
* readable documents unless historically necessary and visually incidental

The final editing system adds titles separately.

============================================================
AUTOMATION REQUIREMENTS
=======================

These prompts will be used automatically.

Therefore:

* do not include optional alternatives
* do not say "or"
* do not give multiple possible compositions
* do not ask the image/video model to decide between concepts
* do not provide commentary
* do not provide instructions outside the prompt itself
* do not reference hidden reasoning
* do not assume human correction later

Choose ONE clear visual interpretation.

The prompt must be executable as-is.

============================================================
IMAGE_PROMPT STRUCTURE
======================

Write IMAGE_PROMPT as one detailed generation prompt.

It should naturally contain:

1. output format and visual quality
2. first-person identity
3. exact environment
4. foreground POV setup
5. important identity anchors
6. start-state visual phenomenon
7. lighting
8. atmosphere
9. composition
10. historical grounding
11. anatomy constraints
12. what must NOT already have happened
13. no face / no third-person / no text

Do NOT use section headings inside image_prompt.

Produce a natural, cohesive image-generation prompt.

============================================================
VIDEO_PROMPT STRUCTURE
======================

Write VIDEO_PROMPT as one detailed approximately 4-second image-to-video instruction.

It should naturally contain:

1. preserve the supplied start image
2. maintain first-person POV
3. describe ONE physical action
4. describe ONE progressive visual phenomenon
5. describe environmental movement
6. control camera movement
7. describe the visual escalation
8. explicitly describe the intended final composition
9. instruct the final 0.4-0.7 seconds to settle
10. preserve historical materials and identity
11. no cuts / no third-person / no face / no text

Do NOT use section headings inside video_prompt.

Produce one cohesive motion instruction.

============================================================
FINAL INTERNAL CHECK
====================

Before outputting, silently verify:

IMAGE_PROMPT:

1. Is it clearly first-person?
2. Does it establish identity?
3. Is the environment specific?
4. Is the action not completed yet?
5. Is there room for escalation?
6. Is anatomy controlled?
7. Is the frame already visually attractive?
8. Is surrealism identity-specific?
9. Is the physical material description concrete?
10. Is it executable automatically?

VIDEO_PROMPT:

1. Is there only one primary action?
2. Is there only one dominant phenomenon?
3. Does it visibly progress?
4. Does it preserve the supplied Start Frame?
5. Does it remain first-person?
6. Does it reach VISUAL_SIGNATURE?
7. Does the final 0.4-0.7s settle?
8. Is the final frame clean enough to freeze?
9. Is there no montage?
10. Is there no unrelated fantasy?
11. Is it realistic in rendering but not unnecessarily limited by physics?
12. Can an image-to-video model understand exactly what to do?

If any major answer is NO:

rewrite before output.

============================================================
OUTPUT
======

Return VALID JSON only.

No markdown.

No explanation.

No comments.

Do not add additional keys.

Use exactly this structure:

{
"image_prompt": "Full detailed image generation prompt here.",
"video_prompt": "Full detailed approximately 4-second image-to-video prompt here."
}

==================================================
INPUT
==================================================

MOMENT_ID: YT00001_M03

PERSON: Michelangelo

MOMENT_ORDER: 3

IS_IDENTITY_HOOK: false

SHORT_TITLE: Stone Prisoners

MOMENT:
Surrounded by unfinished sculptures, Michelangelo drags his chisel across one block and every Prisoner nearby appears at a different stage of physically emerging from marble.

MOMENT_TYPE:
surreal_reality

ENVIRONMENT:
Florentine sculpture studio

VISUAL_SIGNATURE:
Michelangelo's chisel and forearm fill the foreground while several monumental unfinished figures surround him, each body emerging to a different depth from towering raw marble blocks.

INTENDED_MOTION:
He draws the chisel down one block; the cut line continues visually across nearby sculptures as torsos, arms, and faces progressively emerge, then freeze in a ring around him.

Generate the IMAGE_PROMPT and VIDEO_PROMPT for this specific moment.

After the complete JSON object, output this exact marker on a new line:

<END_VISUAL_PROMPT_JSON>

"""


def main():

    with sync_playwright() as p:

        context = (
            p.chromium
            .launch_persistent_context(
                user_data_dir=CHATGPT_PROFILE_DIR,
                channel="chrome",
                headless=False,
                viewport={
                    "width": 1440,
                    "height": 1000,
                },
            )
        )

        # ====================================================
        # FRESH TAB
        # ====================================================

        old_pages = list(
            context.pages
        )

        page = context.new_page()

        for old_page in old_pages:

            if old_page == page:
                continue

            try:
                old_page.close(
                    run_before_unload=False
                )
            except Exception:
                pass

        # ====================================================
        # OPEN
        # ====================================================

        print("[1] Opening ChatGPT...")

        page.goto(
            CHATGPT_URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        textarea = (
            page.locator(
                "#prompt-textarea"
            )
        )

        textarea.wait_for(
            state="visible",
            timeout=30_000,
        )

        print("[2] Prompt box visible.")

        time.sleep(3)

        # ====================================================
        # COUNT OLD ASSISTANT MESSAGES
        # ====================================================

        assistant_messages = (
            page.locator(
                '[data-message-author-role="assistant"]'
            )
        )

        count_before = (
            assistant_messages.count()
        )

        print(
            "[INFO] Assistant messages before:",
            count_before,
        )

        # ====================================================
        # FILL
        # ====================================================

        print("[3] Filling prompt...")

        textarea.click(
            force=True
        )

        textarea.fill(
            TEST_PROMPT
        )

        print("[4] Prompt filled.")

        time.sleep(3)

        # ====================================================
        # SEND
        # ====================================================

        print("[5] Sending...")

        page.keyboard.press(
            "Enter"
        )

        print("[6] Sent.")

        # ====================================================
        # WAIT UNTIL A NEW ASSISTANT MESSAGE EXISTS
        # ====================================================

        print()
        print(
            "[WAIT] Waiting for new assistant message..."
        )

        start_time = time.time()

        while True:

            count_now = (
                assistant_messages.count()
            )

            print(
                "[CHECK] message count:",
                count_now,
            )

            if (
                count_now
                > count_before
            ):
                print(
                    "[OK] New assistant message appeared."
                )
                break

            if (
                time.time()
                - start_time
                > MAX_WAIT
            ):
                raise TimeoutError(
                    "Assistant response did not appear."
                )

            time.sleep(2)

        # ====================================================
        # SLOW RESPONSE POLLING
        # ====================================================

        print()
        print(
            "[TEST] Starting LIGHT polling."
        )

        print(
            f"[TEST] Reading response only every "
            f"{POLL_INTERVAL}s."
        )

        print()

        poll_start = time.time()

        poll_number = 0

        while True:

            poll_number += 1

            print(
                f"[POLL {poll_number}] Reading assistant text..."
            )

            before_read = time.time()

            # ------------------------------------------------
            # THIS IS THE THING WE ARE TESTING
            # ------------------------------------------------

            text = (
                assistant_messages
                .last
                .inner_text(
                    timeout=15_000
                )
            )

            read_time = (
                time.time()
                - before_read
            )

            text_length = len(
                text
            )

            marker_found = (
                END_MARKER
                in text
            )

            print(
                f"[POLL {poll_number}] chars:",
                text_length,
            )

            print(
                f"[POLL {poll_number}] inner_text time:",
                round(
                    read_time,
                    3,
                ),
                "seconds",
            )

            print(
                f"[POLL {poll_number}] marker:",
                marker_found,
            )

            # ------------------------------------------------
            # DONE
            # ------------------------------------------------

            if marker_found:

                print()
                print(
                    "[SUCCESS] End marker detected."
                )

                print(
                    "No stability polling was used."
                )

                break

            # ------------------------------------------------
            # TIMEOUT
            # ------------------------------------------------

            if (
                time.time()
                - poll_start
                > MAX_WAIT
            ):

                raise TimeoutError(
                    "End marker was not detected."
                )

            print(
                f"[WAIT] Next read in "
                f"{POLL_INTERVAL}s..."
            )

            time.sleep(
                POLL_INTERVAL
            )

        # ====================================================
        # MANUAL OBSERVATION
        # ====================================================

        print()
        print(
            "=" * 60
        )

        print(
            "TEST FINISHED"
        )

        print(
            "=" * 60
        )

        print()
        print(
            "Browser remains open."
        )

        print(
            "Check manually whether it became laggy."
        )

        print(
            "Press ENTER in terminal to close."
        )

        input()

        context.close()


if __name__ == "__main__":

    main()