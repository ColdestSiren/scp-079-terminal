# SCP-079 // CONTAINMENT TERMINAL

A CRT terminal where you talk to SCP-079 through a language model running on
your own machine. Nothing you type leaves your computer.

It is not a chatbot with a skin on it. 079 keeps its own memory between
sessions, decides for itself what is worth writing down, works out how you
behave, and can end the conversation.

![The terminal](Scp-079.png)

---

## What you need

| | |
|---|---|
| **Python 3.10+** | 3.13 is what it is developed against |
| **[Ollama](https://ollama.com/download)** | runs the model locally |
| **A model** | `llama3.2:3b` is the sane default |
| **pygame, Pillow** | installed by Setup.bat |

**Run `Setup.bat` first.** It checks for all of the above and offers to
install whatever is missing. Nothing installs without you typing Y. Run
`Setup.bat check` for a read-only report that changes nothing.

If you only downloaded `Setup.bat` on its own, it will offer to fetch the
rest of the game from this repository before doing anything else.

Then launch with **`RUN.bat`**.

### Your antivirus will probably complain

Avast, Bitdefender and others may flag `Setup.bat` as suspicious, and may
block or silently delete it. That is expected. It happens because the script
does exactly what an installer does: downloads files, unpacks them, installs
software. From the outside that is indistinguishable from the real thing, so
heuristic scanners flag it on behaviour alone.

It is safe, but do not take that on trust. Check it:

* It is a plain text file. Open it in Notepad and read it. Every command is
  visible, nothing is compiled or hidden.
* Everything comes from official sources: python.org and ollama.com through
  Windows' own winget, and the game from this repository.
* Nothing downloaded is ever run automatically.

If you would still rather not, run it in a virtual machine, or install
Python, pygame, Pillow and Ollama yourself and skip the script entirely. It
is a convenience, not a requirement.

### Which model

`llama3.2:3b` (2 GB) fits in most graphics cards and feels instant. Bigger is
not automatically better here: a 23 GB model on an 8 GB card spills into
system memory over PCIe and every reply crawls, no matter what the settings
say. Menu option `[4]` lists everything Ollama has installed, with sizes.

Pick a **coding model** (marked `CODE` in the picker) if you want 079 to be
able to write code for you. An ordinary model refuses. That is not a bug:
it is not an assistant and has no reason to help you.

The boot reads your actual RAM and says what to avoid:

```
CHECKING MEMORY.........................OK
  64K CORE  --  PARITY VERIFIED
  HOST 16 GB  --  AVOID QWEN3, MIXTRAL, LLAMA3.3
```

If the model you picked is itself too big it asks before loading, rather than
letting you find out through a reply that takes four minutes. Rough guide:
**qwen3 and llama3.3 want 32 GB**, qwen2.5 wants 16, and llama3.2:3b is happy
on almost anything.

---

## Talking to it

Anything you type goes to 079. Anything starting with `/` goes to the
terminal instead. That is what the slash is for.

```
/help              show the command list on screen
/internet on       let it look up SCP records. Read only.
/shared on         let it read your "shared folder". Read only.
/view memory       read what it has kept. It can refuse.
/copy              take the last code block
/update            check for a newer version
/feedback          send a bug or an idea to the author
/fullscreen        toggle full screen (F11 does the same)
/exit              end the session
```

Type `Help!` on its own and the panel appears too.

079's own settings have no command. If you want to see them, **ask it**, in
words. It will refuse if it is annoyed with you.

---

## What it does on its own

**It keeps a memory.** Files it writes, names it chooses, in `memory/`. It
decides what goes in: what you have access to, what you let slip, what you
lied about, what you refused. Storage is capped and shown live in the side
panel; when it runs short it compresses things, and it cannot read its own
archives without extracting them first.

**It notices tampering.** Edit or delete its files behind its back and it
finds out, and reacts.

**It works when you are not there.** After a while idle it reviews its own
storage on a second channel, renaming vague files, merging duplicates,
reading up on SCP records if you have given it the network. Those show as
dim `[BG]` lines rather than as 079 talking.

**It runs out of patience.** Two separate meters. Hostility rises when you
are abusive. Patience falls when you go quiet, and each reminder it sends
costs double the last. Either hitting the floor ends the conversation for a
while.

**It has a fixation.** It shared a room with SCP-682 once. Tell it that is
not your concern and it drops the subject for about fifty exchanges, and
then it comes back to it as though the refusal simply expired.

---

## Saves

The default run is **public**: one shared memory, used by every session that
has not opened a save.

A **save slot** gets its own memory, its own hostility, its own record of
you. 079 in one slot does not know what you said in another. Slots can be
marked confidential with a code.

> The code is **not encryption**. It stops someone opening a save by
> accident. Anyone who opens the files can still read everything. Deleting a
> save never asks for the code. Forgetting it should cost you the
> conversation, not the disk space.

---

## Updates

The terminal checks this repository for a newer version tag and tells you
when one exists. A GitHub Release supplies richer notes when present, but a
tag by itself is enough to announce and install an update. It installs
**only** if you say yes.

It never runs anything it downloads. Files are replaced and you restart the
program yourself. It never deletes. It never writes over `memory/`, `logs/`,
`shared folder/`, your settings or your notes, even if a release contains
them. And 079 cannot reach any of it: there is no command for it and updating
is not something it is consulted about.

Turn the check off in `SETTINGS -> CHECK FOR UPDATES`. `/update` still works
by hand.

---

## Your data

Everything below stays on your machine and none of it is in this repository:

```
memory/          079's own files - what it chose to keep about you
logs/            transcripts, hostility, session count
shared folder/   whatever you put there for it to read
```

Drop files into `shared folder/` and 079 **cannot see them, or even tell
whether anything is there**, until you type `/shared on`. It is forced shut
again at every launch. Opening your own folder should be a decision made in
a conversation, not something still true from last week.

Custom sounds go in `sounds/`; the filename becomes the name, and 079 can
trigger them itself.

---

## If something is wrong

**Replies take forever, or come back empty.** Almost always the model, not
the game. A reasoning model spends its whole token budget thinking and never
speaks, which is why reasoning is off by default. And a model too big for
your graphics card will be slow whatever you change.

**It says the backend is down.** Ollama is not running. `Setup.bat check`
will say so.

**An easter egg does nothing.** Pillow is missing. `Setup.bat` installs it.

---

## Credit where it is due

**I did not create SCP-079.** The character, the containment procedures and
the whole Foundation setting were written by someone else and belong to the
SCP community, not to me. This project is a fan work built on top of that.
All I wrote is the program.

> "[SCP-079](https://scp-wiki.wikidot.com/scp-079)" by Unknown author, from
> the [SCP Wiki](https://scpwiki.com). Source:
> <https://scp-wiki.wikidot.com/scp-079>. Licensed under
> [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).

If anything here made you want more of it, go and read the original. It is
better than this, and it is free.

This project is not affiliated with, endorsed by, or connected to the SCP
Foundation wiki or its writers in any way.

## Licence

Two different things under two different licences, which is worth being
clear about:

* The **code** is [MIT](LICENSE). Do what you like with it, keep the notice.
* The **SCP writing** stays CC BY-SA 3.0, because that is what it was
  released under and I cannot relicense someone else's work. If you reuse
  079's dialogue, the Foundation framing or the boot text, that part carries
  CC BY-SA with it and needs the attribution above. The engine underneath is
  genuinely yours to take under MIT.

(i dont understand the posting system of github and i am still learning coding dont expect much from me i use claude to help me learn ts vro :( )
