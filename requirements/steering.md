# Josh's steering

Read this before starting work, before dispatching any agent, and after every compaction. It is the only source of intent. Everything else in the repo is agent-written.

Compiled by AI on 2026-10-24 by model GPT-6 Astra (first thread). Completed by AI on 2026-10-25 by model Claude Opus 5.5 with the rescue thread and the planning session, extracted verbatim from the raw transcripts. Quotes preserve Josh's wording, typos included. Automated heartbeat prompts are not Josh's words and are left out. Private conversation links and IDs are omitted; no private house contents are included. Later statements override earlier ones.

Three conversations: the first build thread (23 Oct, Codex), the rescue thread (24 to 25 Oct, Codex), and the planning session (25 Oct, Claude Fable) that produced the current plan.

# First build thread, 23 Oct

## Initial brief

> check https://x.com/ktoya_me/status/2112439926071693741 and https://x.com/_coenen/status/2014359718697799989 tiny.london.
>
> building on [private interior/house modelling chats] i want something similar for rotterdam: an isometric pixel map or smth. in scope: entire gemeente rotterdam. (possibly later entire NL but lets see). first i want you to use inventory all the existing NYC and London versions then do the same for rotterdam using [$josh:better] and [$josh:raise-the-ambition] should publish it on chatGPT sites using 010.jjpcodes.net

> ask questions about scope in first 5 mins if anything unclear

> use SSD for storage, public git repo, MIT license

The proposed distinction between an exploratory map and a selectable city model was rejected:

> this question doesnt' make sense

> yes to reusing lessons and keeping house data private; but also imagine that eventually the house stuff should zoom out into the full 010 pizxel map (and also the idea about pixel map should also have it e.g. reflecting real time weather etc). but NO PERSONAL DATA IN THIS REPO OR PROJECT (other than my name / twitter @) . also use the share tricks from monemap/nice weather/etc with my @ in them and easy copying of screenshots for twitter/instagram

Budget selection:

> Free resources only for now (recommended)

## Lighting and publication

> tiny.london one doesn't have lighting which i think is a big failure. we should have proper lighting

> i mean night lighting. right now tiny.ondon is pure dark and it sucks cos all the building are jjus dark which is not realistic

Corrected domain selection:

> Use 010.jjpcodes.com (recommended)

## Autonomy and quality

> btw set yourself a goal and keep continuing until you are PROUD of the result and it passess [$josh:better] and [$josh:raise-the-ambition] each time without doing unnecessary churn/bloat

> im going to sleep so keep driving autonomously. i want pixel perfect detail, loads of screenshots, MUCH higher resolution than we have already

> and dont forget performance btw must have really fast loading times on all devices lets say like 100ms and same for panning/zooming etc whatever is SOTA whilst still maintianngi the visual quality bar. use [$josh:better] on these metrisc when you come to it. but first make it look good then make it fast

> not sure what metric we should use for "visually good enough" but i would say like "almost as good as google street view/satellite" would be a good rubric. maybe we wanna do visually faithful stuff later so ideally the pixel art/isometric whatever we are calling it thing is a step in a pipeline not just the end results; and then also we can do inrecmemntal improvements. you get the idea?

> btw test primarily in your OWN browser not chrome unless you really have to

> and if the public data is not good enough consider adding other sources within reason and /better compliant. this is like 2 orders of magnitude not detailed enough imo

> consider also using Astra for coordination/planning and Sol 6.1 low/med for implementation if that benefits, is more token efficient. this should not come at the expense of the deliverable's quality tho

## Transport and requirements

> btw i will want accurate public transport, simulated vehicles, but REALTIME accurate trams, trains, buses, metros, etc. plus cutaway view of metro. plus keep all my steering in some kinda requirements folder. capice?

> if you really wanna go nuts then add in marine traffic

## Continued visual review

> some of this stuff doesn't look so good. so keep on checking and keep on improving

The assistant initially misidentified the defects in the attached night close-up. The user corrected that interpretation:

> no the problem is the weird street halfway in the bridge and the jarring contrast between "photographically realistic" streets (not the goal) and the stylistic buildings (the goal)

The attachment is not stored here because it includes private browser chrome. The correction overrides the assistant's earlier interpretation: stylistic buildings are the desired direction; photographic streets are not.

## Bitter Lesson: hard requirement

> btw recall also that maybe new models will come in the future that are better at this than you, so you should design things in a way that its easy for a new model to come along again, understand what you did from first principles, and re-do all the work that its better at. we must be BITTER LESSON PILLED! HARD REQUIREMENT!

## Fidelity and data combination

> overall idea for fidelity: ensure the highest fidelity within reason by sensibly combining as many datasets as necessary to ensrue appropritaley high quatliy data. pareto efficiency type idea

> well remember to think holistically across the entire city not just individual details

## Outcome over verification activity

> btw ensure we do not degrade into proof port and ensure that the worker thread keeps on actually advancing the goal in line with steering and the better/ambition skills

Recorded by AI on 2026-10-24 by model GPT-6. Workers must keep advancing the whole product. Verification supports decisions; archives, counts and repeated local fixes are not the deliverable.

> *proof porn. anyway this assessment (better, raise ambition, correct hill climbing on deliverable vs proof porn) must be invoked at every time you asssess what the worker model is doing

This applies to every manager/worker assessment, including scheduled continuations.

# Rescue thread, 24 to 25 Oct

Josh handed the first thread's work to a new Codex manager.

> i want you to take over my 010 pixel map thread and rescue it. it delivered some okay work but it's got stuck at local minima and it's misunderstood the brief.
>
> complaint/s: buildings are weird colored and nowhere near detail enough
> cars are totally retsrded with driving patterns
> no cyclists
> quality is really nowhere near the examples we gave - this is much more a shitty 3d map than a mini pixelated version of the city
>
> ui chrome is terrible and noisy on phone and hides the map, hasn't been tested properly
> metro cutaway looks terrible and doesn't seem to have any metros?
> anyway you are capable of figuring out ALL the quality issues against my brief yourself these are just some pointers
>
> i want you to direct the work using the pattern from this tweet
> https://x.com/pvncher/status/2113794328690647521?s=46
> set up a cloud thread for the implementation work(ers) you just manage. you can even move yourself to the cloud if you want
>
> ensure you extract steering and always check against it becuase the model didn't do a good job of that so far
>
> and again keep working until it's GOOD and you are PROUD

> the work and approach must be deep and holistic btw not tiny patches

> compare with how the prior art versions did it btw?

> why did you stop your turn btw. you need to use the mechanisms in the tweet to keep working until the entire project is complete.
>
> i like our 3d idea but it should be combined with the model stuff you found to ensure we have something that's at the pareto optimal principle of image quality ; realism; and blazing fast performance (image quality most important; we shouldn't "guess" or "invent" parts of the city they should all look basically perfect jnkeeping with our style as you zoom in

> not sure what happened with car and bicyclist routes but we should be making use of eg vector maps of all the routes to ensure that they are locgicsl routes for cars and bikes (usually separate in rotterdam)
>
> again: keep thinking holistically about the whole body of work; keep using [$josh:better] and [$josh:raise-the-ambition]

> https://x.com/raunofreiberg/status/2112875577388712123?s=46 random new requirement: we should add an appropriate og:video tag for our site too as we go.

> btw ensure we do not degrade into proof port and ensure that the worker thread keeps on actually advancing the goal in line with steering and the better/ambition skills

> *proof porn. anyway this assessment (better, raise ambition, correct hill climbing on deliverable vs proof porn) must be invoked at every time you asssess what the worker model is doing

> stop being regarded continue locally then

> also figure out why they are rate limited? you can also use mac mini? this is dumb?

> wtf is going on what have you been wasting tokens on. anything at all?

> have you made any progress whatsoever?

> it looks exactly the same as how it was when i set you off on this task? literally every single failure mode i asked about is still there? unacceptable?

> pause. tell me what you have been doing the last N turns how many tokens have been spent and hwat you ahve actually produced. something or nothing. or just 1000 turns of proof porn

> well why can't you fix it fucking properly?

> well why can't you fix it fucking properly? explain how you will fix it properly not just self-flagellation?

> well set that up properly and POC it? drive it in whatever way will actually GET RESULTS, but use cloud agent threads to execute it to save resources on this machine. figure out which implementation owner thread is in charge (presumably you). and keep track of things properly so that this doesn't degrade further into proof porn or just useless iteration again? also tell me which neighbourhood you are actually working on so i can test it? also make sure to LOOK at the results and use [$josh:better] to design a proper verification process (including SLOs on load times, its currently insanely slow) with a proper way for the agent implementing stuff (you) to understand how to keep track of what has been done and to see if the improvements actually work and are improving or not? same thing with organizing the work, come up with a coherent first principles plan to actually create this, in the correct and relevant order for the deliverable. you are a frontier model and this level of failure to perform is unacceptable

On the manager saying it would set up "a bounded production test with one accountable implementation owner":

> no i mean just keep driving the ENTIRE project and do it PROPERLY and TELL me which neighbourhood you are doing first. you are still in charge of the entire product e2e and prior steering still applies

Viewing https://010.jjpcodes.com/?lat=51.90960&lon=4.44782&span=40&bearing=120&light=day:

> are you using the correct level of granularity and the correct orthogonal componetns to produce the work? what are you doing differnetly to the upstream projects and what is better or worse?

> fix the scheduled task its dumb

> what model are the cloud agents using?

> find out? make sure they are using 6.1 sol medium?

> the model is retarded and is now handing it off to new sub-threads or something? what the fuck are youdoing

> what's going on. this looks like typical AI slop imagery?

On the manager's reply that the candidate had turned grey roofs terracotta, removed a solar array and turned rooftop louvres into brickwork:

> but look at the ROADS too

> but also look how upstream did it?

> honeslty just stop fuck this fable will do a better job. summarzie everything you've done so far in the repo somewhere so a new smarter model can take over FROM FIRST PRINCIPLES and basically start from scratch (doing a better job than this complete waste of tokens

# Planning session, 25 Oct (Claude Fable)

> take a look at the codex threads working on the 010 map. they were a complete fucking disaster basically. see how you can take it over based on my steering and make it actually good. come up with a holistic plan that we can delegate to opus 5.5 to orchestrate (and use its own judgement to make stuff better if we run into issues, its smart enough for that) and let retarded autistic sol 6.1 medium implement

On a proposal to ship a pre-rendered pixel-art pyramid and lose free rotation:

> well this needs more decision work to be something more properly thought out

On GPU spend for the whole city:

> again thinking too early we are not ther eyet

On starting a clean repository:

> no just use a branch who cares

On teacher images from ChatGPT Pro or a capped Gemini key:

> no gemini whatsoever ever. find out how you and other agnets keep finding out about this and spawn a new task to make it so that does not happen i dont want agents spending fucking money. use chatGPT pro image generation (its all free in our plan and we have a ton of tokens) if you need that but i'm not sure if it's the right option honeslty. this is not a proper plan yet yand you are locking in way too many decisions

On drafting the plan "as a decision programme rather than a fixed design":

> well no thats retarded too. act like a principal engineer would do at a faang when given the project. /better and /raise-the-ambition

On "One orthographic camera, 45° tilt, bearing chosen once":

> does this mean we can't rotate the map?

On style being the critical path:

> tricky part but 1) we have ~free imagegen models (chatGPT imagegen via luna/sol/astra, not sure which models they use and how much they cost); also macbook can run models but.......... its not that powerful compared toe H100s.
>
> question about tthe image models tho is like........... is this really the best mthod?
>
> other problem with lighting in the first iterations from codex is that it just made all buildings out of a grid of windows which is stupid
>
> i PREFER having a fully 3d model because then we can use it for other projects later on (like GTA rotterdam or smth) but we should discuss tradeoffs here?

On procedural rendering from the 3D model as an honest baseline:

> idk i think we should at least compare? becuase fully. 3d model of entire city in full 3d with high quality imagery might be better?

On an image model repainting the render with structure locked:

> yeah and the problem i saw in codex was they just like hallucinated random lines on roads that vaguely looked like tram tracks but not really isntead of like........ well tram tracks and road markings
>
> ok i think that the 3d vs modelling tradeoffs are fine. i think what you should be doing here is POCing both options and seeing which version (or hybrid) is most promising? or letting opus POC is more realistically

On the planner narrowing that to "tram tracks and road markings come from data":

> well the point is more holistic these are just examples of the failure mode..........

> i'm going to sleep start working on this overnight
