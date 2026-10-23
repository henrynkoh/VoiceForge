# Email campaign, three messages

## Email 1, day 0: the number

**Subject:** 4 cents for a 30-minute audiobook
**Preheader:** The split that did the work, and what it measured.

Hi,

Last week I narrated a 30-minute book in my own cloned voice. It cost four cents.

Not because I found a cheaper voice. Because I stopped sending everything to the expensive one.

The setup: my voice cloned twice, once on a cloud service that bills per character, once on a free open-source studio running on my own laptop.

The split: English paragraphs to the free local clone, Korean paragraphs to the cloud clone. Two short pieces, the series opening and the verse quotation, went to the cloud as well, because those two had to be flawless.

The ledger: 229 credits, about four cents, all cloud would have been 17,200 credits.

Full breakdown, including the commands: [TUTORIAL](https://github.com/henrynkoh/VoiceForge/blob/main/TUTORIAL.md)

Henry

## Email 2, day 3: the surprise

**Subject:** The free clone was closer to me than the paid one
**Preheader:** 0.959 versus 0.815, and why that is not the whole story.

Hi,

A measurement worth sharing.

I compared both clones against recordings of my actual voice using a speaker-verification embedding. Different speakers score around 0.63 to 0.71. My cloud clone scored 0.815. My free local clone scored 0.959.

So the free one matched my timbre more closely. And it still sounded worse, for a reason that had nothing to do with timbre: it read 35% faster than I speak.

Slowing it to my own rate, 13.3 characters per second, fixed what my ears had been calling a quality problem.

The lesson I keep relearning: measure the thing you are complaining about before you replace the tool.

[The measured comparison](https://github.com/henrynkoh/VoiceForge/blob/main/TUTORIAL.md)

Henry

## Email 3, day 7: the invitation

**Subject:** What would you narrate, if it were free
**Preheader:** Quickstart is five minutes. No account needed for the free path.

Hi,

One question, because it changed my own backlog:

What would you narrate if it cost nothing?

For me the answer was a nine-chapter Bible study that had been a written outline for two years, plus a four-part series cut of the same material. Both exist now.

Five minutes to try it:

1. Install Python and, for the free engine, Docker.
2. Run `python3 -m voiceforge.app` and add a voice.
3. Paste a paragraph and press Generate.

If the paragraph sounds right, render a chapter. If the chapter sounds right, render the book.

[Quickstart](https://github.com/henrynkoh/VoiceForge/blob/main/QUICKSTART.md) · [Landing page](https://henrynkoh.github.io/VoiceForge/)

Reply and tell me what you would make. I read every one.

Henry
