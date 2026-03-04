from __future__ import annotations

import secrets
import string

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from core.models import Alias
from core.models import Bot
from core.models import Channel
from core.models import Command as BotCommand
from core.models import Counter
from core.models import Skill

SEED_DATA = {
    "users": [
        {
            "username": "avalonstar",
            "is_superuser": True,
            "is_staff": True,
        },
        {
            "username": "spoonee",
            "is_superuser": False,
            "is_staff": True,
        },
    ],
    "bots": [
        {
            "name": "Elsydeon",
            "twitch_user_id": "66977097",
            "twitch_username": "elsydeon",
            "channels": [
                {
                    "twitch_channel_id": "38981465",
                    "twitch_channel_name": "avalonstar",
                },
            ],
        },
        {
            "name": "WorldFriendshipBot",
            "twitch_user_id": "149214941",
            "twitch_username": "worldfriendshipbot",
            "channels": [
                {
                    "twitch_channel_id": "78238052",
                    "twitch_channel_name": "spoonee",
                },
            ],
        },
    ],
}


def generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Command(BaseCommand):
    help = "Seed initial users, bots, and channels."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding database..."))

        for user_data in SEED_DATA["users"]:
            username = user_data["username"]
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "is_superuser": user_data["is_superuser"],
                    "is_staff": user_data["is_staff"],
                },
            )

            if created:
                password = generate_password()
                user.set_password(password)
                user.save()
                role = "superuser" if user_data["is_superuser"] else "staff"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Created {role} user: {username} (password: {password})"
                    )
                )
            else:
                self.stdout.write(f"  User already exists: {username}")

        for bot_data in SEED_DATA["bots"]:
            bot, created = Bot.objects.get_or_create(
                twitch_user_id=bot_data["twitch_user_id"],
                defaults={
                    "name": bot_data["name"],
                    "twitch_username": bot_data["twitch_username"],
                },
            )

            status = "Created" if created else "Exists"
            self.stdout.write(
                self.style.SUCCESS(f"  {status} bot: {bot.name} ({bot.twitch_user_id})")
            )

            for ch_data in bot_data["channels"]:
                channel, ch_created = Channel.objects.get_or_create(
                    bot=bot,
                    twitch_channel_id=ch_data["twitch_channel_id"],
                    defaults={
                        "twitch_channel_name": ch_data["twitch_channel_name"],
                    },
                )

                status = "Created" if ch_created else "Exists"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"    {status} channel: #{channel.twitch_channel_name}"
                    )
                )

        # --- Seed Spoonee's channel-specific commands ---

        try:
            spoonee_channel = Channel.objects.get(twitch_channel_name="spoonee")
        except Channel.DoesNotExist:
            spoonee_channel = None

        if spoonee_channel:
            self._seed_spoonee_commands(spoonee_channel)

        # --- Seed Avalonstar's channel-specific commands ---

        try:
            avalonstar_channel = Channel.objects.get(twitch_channel_name="avalonstar")
        except Channel.DoesNotExist:
            avalonstar_channel = None

        if avalonstar_channel:
            self._seed_avalonstar_commands(avalonstar_channel)

        # --- Seed skills for all active channels ---

        self._seed_skills()

        self.stdout.write(self.style.SUCCESS("\nSeed complete."))
        self.stdout.write(
            "Next: visit /setup/<bot_id>/ to connect bot and channel tokens."
        )

    def _seed_spoonee_commands(self, channel):
        """Seed Spoonee's channel-specific commands."""
        spoonee_commands = [
            {
                "name": "conch",
                "type": BotCommand.Type.RANDOM_LIST,
                "config": {
                    "prefix": "\U0001f41a ",
                    "responses": [
                        "No.",
                        "Maybe someday.",
                        "Nothing.",
                        "Neither.",
                        "Follow the seahorse.",
                        "I don't think so.",
                        "Yes.",
                        "Try asking again.",
                        "Noooo~OOOO.( \u0361\u00b0 \u035c\u0296 \u0361\u00b0)",
                        "If you try really hard.",
                        "Not even I know that.",
                        "It is certain.",
                        "Only time will tell.",
                        "The ocean tells me it is so.",
                        "Of course.",
                        "I can practically guarantee it.",
                        "I believe so.",
                        "Nothing says otherwise.",
                        "It is your fate.",
                    ],
                },
            },
            {
                "name": "parrotfact",
                "type": BotCommand.Type.RANDOM_LIST,
                "config": {
                    "responses": [
                        "#1: There are over 350 different types of parrots, including Macaws, Amazons, African greys, lorikeets, lovebirds, conures, cockatoos, and many others.",
                        "#2: The African grey parrot (Psittacus erithacus) is the most accomplished user of human speech in the animal world.",
                        "#3: All parrots have curved beaks and all are zygodactyls, meaning they have four toes on each foot, two pointing forward and two projecting backward.",
                        "#4: Most parrots eat fruit, flowers, buds, nuts, seeds, and some small creatures such as insects.",
                        "#5: The genders of African grey parrots have no physical differences from one another. Other than waiting for the parrot to lay an egg, a blood test is the only way to tell what gender they are.",
                        "#6: African greys have red tail feathers, which are used to trick predators into going after their tail instead of their body.",
                        "#7: African greys can live 40-60 years in captivity, but typically live 20-30 years in the wild.",
                        "#8. African greys who are around humans can learn hundreds of words over their lifetime.",
                        "#9. African greys are also highly intelligent, having been shown to perform at the cognitive level of a 4-6 year old child in some tasks, including differentiating between objects, colors, materials, and shapes.",
                        "#10. African greys are monogomous.",
                        "#11. Most parrots are social birds that live in groups called flocks. African grey parrots live in flocks with as many as 20 to 30 birds.",
                        "#12. A parrot's eyes dilate when it is stimulated (from tasting food, playing with toys, watching an interesting object or person, etc).",
                        "#13. Cockatoos have a group of feathers on top of their heads that they can move. When on full display, these feathers resemble a mohawk. The cockatoo can also retract the feathers so they lay flat against their heads.",
                        '#14. Alex, the African grey trained by Dr. Irene Pepperburg, was said to be the most intelligent bird ever studied. By the age of 23, Alex could identify 50 different objects and recognize quantities up to six. He could also distinguish seven colors and five shapes, and understand the concepts of "bigger," "smaller," "same," and "different."',
                        '#15. In July 2005, Dr. Irene Pepperberg reported that Alex, the African Grey, actually understood the concept of zero. If asked the difference between two objects, he would give the correct answer; but if there was no difference between the objects, he said "none."',
                        "#16. Parrots have also been considered sacred. The Moche people of ancient Peru worshipped birds and often depicted parrots in their art.",
                        "#17. Parrots that are bred for pets are usually hand-fed or otherwise accustomed to interacting with people from a young age to help ensure they will be tame and trusting.",
                        "#18. Parrots do not have vocal cords. They actually make sound by expelling air across the mouth of the bifurcated trachea, in the organ called the syrinx. Different sounds are produced by changing the depth and shape of the trachea.",
                        "#19. African greys are actually capable of growling, and do so when they are frightened or very angry.",
                        '#20. Parrots don\'t enjoy being petted front-to-back like cats or dogs, but sometimes like receiving "scratches," or the act of ruffling their feathers gently from back-to-front.',
                        "#21. When an African grey is standing on one foot with their other foot tucked under their breast, it means they are very relaxed.",
                        '#22. When parrots clean themselves, it\'s called "preening." To preen, the parrot rubs their head against the base of their feathers, releasing oil from a gland that they then spread onto their feathers using their tongue.',
                        "#23. African grey parrots love to hang upside down. They will do this when happy and content, and of course, playing with their toys!",
                        "#24. Parrots sneeze and yawn, just like humans!",
                        "#25. Young African greys are born with grey irises. But as they reach maturity, the African grey's iris turns lighter, becoming more of a faded yellow.",
                    ],
                },
            },
            {
                "name": "getyeflask",
                "type": BotCommand.Type.LOTTERY,
                "user_cooldown_seconds": 3600,
                "config": {
                    "odds": 2,
                    "success": "$(user) - YOU GET YE FLASK! bardHype bardHype bardHype",
                    "failure": "You can't get ye flask, $(user)! bardPls",
                    "cooldown_response": "$(user), you can only try to get ye flask once per hour. You have $(remaining) seconds left.",
                },
            },
        ]

        for cmd_data in spoonee_commands:
            defaults = {
                "type": cmd_data["type"],
                "config": cmd_data["config"],
                "created_by": "spoonee",
            }
            if "cooldown_seconds" in cmd_data:
                defaults["cooldown_seconds"] = cmd_data["cooldown_seconds"]
            if "user_cooldown_seconds" in cmd_data:
                defaults["user_cooldown_seconds"] = cmd_data[
                    "user_cooldown_seconds"
                ]
            cmd, created = BotCommand.objects.update_or_create(
                channel=channel,
                name=cmd_data["name"],
                defaults=defaults,
            )

            status = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"    {status} command: !{cmd.name} ({cmd.type})"
                )
            )

        # --- Counters ---

        spoonee_counters = [
            {"name": "death", "label": "Deaths"},
            {"name": "scare", "label": "Scares"},
        ]

        for counter_data in spoonee_counters:
            counter, created = Counter.objects.get_or_create(
                channel=channel,
                name=counter_data["name"],
                defaults={"value": 0, "label": counter_data["label"]},
            )

            status = "Created" if created else "Exists"
            self.stdout.write(
                self.style.SUCCESS(
                    f"    {status} counter: {counter.name} ({counter.label})"
                )
            )

        # --- Aliases (counter shortcuts) ---

        spoonee_aliases = [
            {"name": "ct", "target": "count death"},
            {"name": "countadd", "target": "count death +"},
            {"name": "addscare", "target": "count scare +"},
            {"name": "scare", "target": "count scare"},
            {"name": "followcheck", "target": "followage"},
            {"name": "checkme", "target": "followage"},
        ]

        for alias_data in spoonee_aliases:
            alias, created = Alias.objects.get_or_create(
                channel=channel,
                name=alias_data["name"],
                defaults={"target": alias_data["target"]},
            )

            status = "Created" if created else "Exists"
            self.stdout.write(
                self.style.SUCCESS(
                    f"    {status} alias: !{alias.name} → !{alias.target}"
                )
            )

    def _seed_avalonstar_commands(self, channel):
        """Seed Avalonstar's channel-specific commands (from Moobot export)."""
        avalonstar_commands = [
            {"name": "2turn", "response": "Bounce, Dig, Dive, Fly, Freeze Shock, Geomancy, Ice Burn, Phantom Force, Razor Wind, Shadow Force, Skull Bash, Sky Attack, Solar Beam, Solar Blade, Sky Drop, Meteor Beam, and Electro Shot. If you're including moves that take a turn to recharge after attacking, then also Blast Burn, Frenzy Plant, Giga Impact, Hydro Cannon, Hyper Beam, Prismatic Laser, Roar of Time, and Rock Wreaker."},
            {"name": "anniversary", "response": "avalonSTARWHEE Avalonstar.com is 25 years old! (9/28) To celebrate starting on 9/23 we are selling out for SUBtember! All your wonderful gift subs and new subs can be put towards incentives that will get Bryan to do some fun and silly things. Just slap that GIFT SUB button or Sub for the first time to get your hands on some beautiful emotes and join the shenanigans today. avalonEUREKA Here's the list! avalonNOTE https://gist.github.com/bryanveloso/012102c7914f3d673d67e2c78ca83dab"},
            {"name": "anthem", "response": "Go check out our very own anthem, Rise of the Crusaders! An Avalonstar and Tiasu production: [ riseofthecrusaders.tiasu.com ]", "use_count": 3},
            {"name": "archive", "response": "View some of our old streams now preserved on YouTube! avalonDAISHOURI https://www.youtube.com/channel/UChmexIn8w3SVSzL_WlBQR1Q"},
            {"name": "avln", "response": "AVLN is Avalonstar's Final Fantasy XIV Free Company whose membership is composed of members of this Twitch community. While membership is open, it is contingent on 1) your attitude and demeanor, 2) your time spent as a member of the community, 3) common sense rules of respect.", "enabled": False, "use_count": 6},
            {"name": "balls", "response": "we have the ball avalonSMUG ~ ball dropped avalonBLANK ~ we have the ball avalonSMUG ~ ball dropped avalonBLANK", "use_count": 5},
            {"name": "birds", "response": "avalonSPOOK BIRDS!? WHY DID IT HAVE TO BE BIRDS!? avalonWHY", "use_count": 1},
            {"name": "blank", "response": "I'm in avalonBLANK doing avalonBLANK with avalonBLANK so I can avalonBLANK but then avalonBLANK came with avalonBLANK and avalonBLANK went down and it was just super avalonBLANK avalonBLANK"},
            {"name": "blind", "response": "would like to remind you that this is a blind run! avalonBLIND . So please no tips or spoilers unless Bryan explicitly asks for them. Thank you! avalonHUG", "use_count": 29},
            {"name": "bosses", "response": "SKONG BOSSES DOWNED avalonFITE : Moss Mother (2), Bell Beast (3), Lace (4), Fourth Chorus (1), Moorwing (30), Splinter Sister (11), Skull Tyrant #2 (4), Widow (20), Great Conchflies (1), Skull Tyrant #1 (1), Last Judge (43/51), Clockwork Dancers (3), Signis & Gron (6), Savage Beastfly (3), Phantom (5), Beastfly 2 Electric Boogaloo (5), Lace #2 (31), Great Conchfly (3), Groal the Great (9), Broodmother (4), Disgraced Chef Lugoli (4), Moss Mother x2 (1), First Sinner (17), Father of Flame (3)..."},
            {"name": "bosses2", "response": "SKONG BOSSES CONTINUED: Second Sentinel (4), Grand Mother Silk (4), Seth (16), Nyleth (12), The Unraveled (3), Palestag (1), Lost Garmond (4), Gronn(?, 2), Plasmafied Zango (2), Khaan (1), Karmelita (35?), Tormented Trobbio (11), Clover Dancers (5). Pinstress (6), Voltwyrm (1), Lost Lace (21)"},
            {"name": "brainpower", "response": "\u2200\u2200\u2200\u2200-\u2200\u2200\u2200-\u2200-O\u018e\u018e\u018e\u018e oo-oo-oo-ooo-O\u017f-\u2200-\u018e-I-\u018e-\u2200-\u018e\u2200\u2200\u2200\u2200 \u01dd\u01dd\u01dd-\u01dd\u01dd-\u01dd\u01dd\u01dd-\u018e -\u2200-\u2229-\u2229-\u2200-\u2200-O-\u018e\u2200\u2200 oooooooooooo-O\u017f -\u2229-\u2200-I-\u2200-\u2200-\u018e\u2200\u2200\u2200\u2200 oooooooooo-O avalonOMG", "use_count": 14},
            {"name": "break", "response": "Hey Bryan, it's time to take a break. avalonSIP"},
            {"name": "coworking", "response": "I am doing a professional. avalonARTSY"},
            {"name": "design", "response": "I used to be a professional designer, here's my portfolio on Dribbble [ https://dribbble.com/bryan ] ."},
            {"name": "destiny", "response": "Join AVLN and the Crusaders of Avalonstar clan in Destiny 2! [ https://www.bungie.net/en/ClanV2/Index?groupId=2096845 ]", "use_count": 19},
            {"name": "discord", "response": "Gather with us in our Discord! If you're a subscriber, in the desktop application, go to \"Settings\" > \"Connections\", sync, and join the server! Otherwise, enter here: [ https://discord.gg/avalonstar ] \u2014 Please remember that ALL chat rules apply to the Discord. Don't be a dick.", "use_count": 124},
            {"name": "fav3", "response": "Bryan's 3 favorites are: Umbreon, Vaporeon, and Espeon", "enabled": False},
            {"name": "ffbot", "response": "Wanna play!? Type !join to participate in the stream! You don't have to be on screen to gain experience. Make sure you !hire chars you want. And check your !stats (Elsydeon will share with you your stats in chat) !freehires are every 50 wins and a !reset (or ascend) is every 100 wins. avalonEUREKA Generally we do this during Bryan's coworking streams or when he's afk for meetings. For more info use !ffdoc|!ffcards|"},
            {"name": "ffcards", "response": "FFBot Card Reference: https://gist.github.com/bryanveloso/e1209bb527037cd1b702116f22bd8d0c"},
            {"name": "ffdoc", "response": "avalonEUREKA You'll find all the info you need on the Seasons and Character's here. Remember to type !ffbot for all the other info you might be looking for! https://docs.google.com/spreadsheets/d/1abh6YTNTMdqdXdSIc0u8vutpzkcRQIoNAL2sO5K9QKY/edit?gid=1799328441#gid=1799328441 / S4 JOBS: https://docs.google.com/spreadsheets/d/1p2SZAHVN_xpxudqkTt3xcbsKILle7GEe7rluDQM1Zcw/edit?gid=0#gid=0"},
            {"name": "ffxiv", "response": "Bryan plays Final Fantasy XIV on \"Famfrit\" which is in the \"Primal\" data center, as \"Elsydeon Detis\" and \"Ava Liang\" He mains Dark Knight and is a member of the Free Company, <<AVLN>>.", "use_count": 13},
            {"name": "first", "response": "This is Bryan's first time playing. Please be respectful of that fact and ask before giving any hints or tips. Unsolicited advice will be purged. Further breaking of this rule will result in a timeout and possible ban."},
            {"name": "hammers", "response": "Before I visited Avalonstar, my village did not know of the wonders of hammers. We often used sticks, bricks, or cousin William's thick forehead to drive nails. Avalonstar came through with lightning-fast delivery of hammers to me and to all of my friends and loved ones. Thank you Avalonstar."},
            {"name": "helloteam", "response": "This is the Hello! Team Cast [ http://twitch.tv/helloteamcast ] Aftercast! All of the games we'll be playing tonight will be between the people you see on screen. Have fun with memes you won't get and check out the cast every other Saturday! ^-^", "use_count": 19},
            {"name": "holy", "response": "https://clips.twitch.tv/HomelySucculentEndiveFloof"},
            {"name": "hug", "response": "$(user) gives $(target) a big hug. avalonHUG", "use_count": 6},
            {"name": "hydrate", "response": "avalonEUREKA make sure you stay hydrated, Bryan and chat! avalonSIP avalonKANPAI"},
            {"name": "ironmon", "response": "avalonEUREKA Looking to check out the rules for this Ironmon? Check them out here https://gist.github.com/valiant-code/adb18d248fa0fae7da6b639e2ee8f9c1#kaizo-ironmon-ruleset"},
            {"name": "kaizo", "response": "Bryan is playing Kaizomon. Where everything you knew about Pokemon was turned upside down and randomized. Enjoy the wild ride. You can find the rules here. avalonEUREKA https://gist.github.com/valiant-code/adb18d248fa0fae7da6b639e2ee8f9c1"},
            {"name": "lastrun", "response": "https://clips.twitch.tv/EnthusiasticFaithfulGarageMikeHogu-COQsp9_2a3seKMBr"},
            {"name": "lurk", "response": "Looks like somebody wants to get cozy. Enjoy your lurk, $(user)! avalonCOZY"},
            {"name": "machinima", "response": "Not sure what's going on right now? Neither do we. avalonDERP Welcome to live machinima recording on Avalonstar! On days like today, Bryan will be mostly interacting in chat, as to not mess up the audio for the footage. avalonSHY Here's what we've made in the past: [ https://www.youtube.com/watch?v=RZeL76U36p8&list=PL8AEA9t0nugPolkqhI6rbwx9mcbUWGXp4 ]", "use_count": 5},
            {"name": "mastery", "response": "FFBot Mastery Levels: 5, 12, 20, 28, 36, 50"},
            {"name": "miq", "response": "GOTCHA BITCH. ($(count.get miq) bitches have been gotcha'ed.) avalonSMUG", "use_count": 255},
            {"name": "modlist", "response": "avalonEUREKA you can find all the mods I'm using in Terraria here. (minus the MP mods) https://steamcommunity.com/sharedfiles/filedetails/?id=3005040658"},
            {"name": "monhun", "response": "Bryan's Hunter ID: C57A59J9 // Crusaders Squad ID: XF9434XP"},
            {"name": "nakama", "response": "Bryan is a part of Nakama, a Twitch team that focuses on camaraderie and collaboration, aka Twitch's Multitap. These broadcasters are good friends and great people, so check them out! [ http://twitch.tv/team/nakamateam ]", "use_count": 58},
            {"name": "pet", "response": "avalonRAGE P E T avalonRAGE T H E avalonRAGE L A L A avalonRAGE (The lala has been pet $(count.get pet) times.) avalonRAGE P E T avalonRAGE T H E avalonRAGE L A L A avalonRAGE", "enabled": False, "use_count": 222},
            {"name": "platforms", "response": "Want to play? Steam: Avalonstar \u2022 PSN: AvalonstarTV \u2022 Switch: SW-2833-7397-3889", "use_count": 7},
            {"name": "rainwave", "response": "The music you're listening to is from [ https://rainwave.cc/game/ ]! Go there if you'd like to request a track to be played on stream!"},
            {"name": "rpgs", "response": "A list of all the RPGs I've beaten in my lifetime. Also rankings: https://gist.github.com/bryanveloso/4244350 ( read: Don't @ me. avalonBAKA )", "use_count": 1},
            {"name": "rules", "response": "Rule #3 - We reserve the right to purge you for being a dick. Don't be a dick. Arguing with us about being purged counts as being a dick. Don't be a dick. Seriously.", "use_count": 8},
            {"name": "salt", "response": "The salt stocks have risen $(count.get salt) times.", "use_count": 6},
            {"name": "sellout", "response": "avalonEUREKA Did you know that if you have Amazon Prime you can link your Twitch and get a free sub? avalonPOG Why not use that sub here to get 60 of the best damn emotes on twitch. Just go to twitch.tv/products/avalonstar_3000 now.", "use_count": 8},
            {"name": "silentmode", "response": "Bryan's playing this game as if he were on his couch in front of the TV, the focus being more on the game than the streamer. But talk to Bryan and he'll talk to you! Otherwise sit back and enjoy $(game).", "use_count": 7},
            {"name": "spoilers", "response": "Please do not spoil the game's story, content, or mechanics. More importantly, please do not lead me on (as in: telling me what's coming up, etc.). React WITH us, not BEFORE us. By reading this message and choosing to ignore it, you agree to welcome the subsequent takedown with open arms.", "use_count": 2},
            {"name": "spoonee", "response": "avalonBLANK I avalonBLANK WANT avalonBLANK TO avalonBLANK RIDE avalonBLANK MY avalonBLANK CHOCOBO avalonBLANK ALL avalonBLANK DAY avalonBLANK", "use_count": 1},
            {"name": "steamid", "response": "76561198009545200"},
            {"name": "sub", "response": "avalonARTSY Do avalonOWO it avalonV for avalonCOZY her avalonBLESS"},
            {"name": "tomthefuck", "response": "Times we haven't questioned what Tom said: $(count.get tomthefuck) avalonUH", "use_count": 65},
            {"name": "trial", "response": "Wanna try out Final Fantasy XIV? Follow this link for a trial! You can play until level 70 with no limitations on game time! Now with the award winning expansion Stormblood! (We're on the \"Famfrit\" server which is in the \"Primal\" data center.) [ http://freetrial.finalfantasyxiv.com/gb/ ]", "use_count": 14},
            {"name": "uma", "response": "Umamusume Trainer ID: 765 712 584 985"},
            {"name": "waah", "response": "avalonWAAH WAAH ($(user) looks at you in surprise.) avalonWAAH WAAH ($(user) looks at you in surprise.) avalonWAAH WAAH ($(user) looks at you in surprise.) avalonWAAH WAAH ($(user) looks at you in surprise.) avalonWAAH WAAH ($(user) looks at you in surprise.) avalonWAAH WAAH ($(user) looks at you in surprise.)", "use_count": 79},
            {"name": "wheel", "response": "Let's take a spin on the DAISHOUWHEEL. Long-time community members have chosen games for Bryan to play and when the wheel chooses a game, he has to play it. Our current game is: Cat Quest"},
            {"name": "willthefuck", "response": "Will has uttered $(count.get willthefuck) Willisms.", "use_count": 117},
            {"name": "woah", "response": "avalonWAAH WOAH (@herdyderp looks at you in surprise.)"},
            {"name": "youtube", "response": "Bryan vlogs and makes UI-related Final Fantasy XIV videos on YouTube! Go to [ http://youtube.com/avalonstar ] and make sure to like and subscribe! :3"},
        ]

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n  Seeding Avalonstar commands ({len(avalonstar_commands)})..."
            )
        )

        for cmd_data in avalonstar_commands:
            defaults = {
                "response": cmd_data["response"],
                "created_by": "avalonstar",
            }
            if "enabled" in cmd_data:
                defaults["enabled"] = cmd_data["enabled"]
            if "use_count" in cmd_data:
                defaults["use_count"] = cmd_data["use_count"]

            cmd, created = BotCommand.objects.get_or_create(
                channel=channel,
                name=cmd_data["name"],
                defaults=defaults,
            )

            if created:
                status = "Created"
                if not cmd_data.get("enabled", True):
                    status = "Created (disabled)"
            else:
                status = "Exists"
            self.stdout.write(
                self.style.SUCCESS(f"    {status} command: !{cmd.name}")
            )

        # --- Counters ---

        avalonstar_counters = [
            {"name": "miq", "value": 255, "label": "Miq"},
            {"name": "pet", "value": 222, "label": "Pet"},
            {"name": "salt", "value": 6, "label": "Salt"},
            {"name": "tomthefuck", "value": 65, "label": "Tomthefuck"},
            {"name": "willthefuck", "value": 117, "label": "Willthefuck"},
        ]

        for counter_data in avalonstar_counters:
            counter, created = Counter.objects.get_or_create(
                channel=channel,
                name=counter_data["name"],
                defaults={
                    "value": counter_data["value"],
                    "label": counter_data["label"],
                },
            )

            status = "Created" if created else "Exists"
            self.stdout.write(
                self.style.SUCCESS(
                    f"    {status} counter: {counter.name}"
                    f" (value={counter_data['value']})"
                )
            )

        # --- Aliases ---

        avalonstar_aliases = [
            {"name": "checkme", "target": "followage"},
        ]

        for alias_data in avalonstar_aliases:
            alias, created = Alias.objects.get_or_create(
                channel=channel,
                name=alias_data["name"],
                defaults={"target": alias_data["target"]},
            )

            status = "Created" if created else "Exists"
            self.stdout.write(
                self.style.SUCCESS(
                    f"    {status} alias: !{alias.name} \u2192 !{alias.target}"
                )
            )

    def _seed_skills(self):
        """Seed skill records for all active channels."""
        skills_to_seed = [
            {"name": "followage"},
            {"name": "spoons"},
        ]

        for channel in Channel.objects.filter(is_active=True):
            for skill_data in skills_to_seed:
                skill, created = Skill.objects.get_or_create(
                    channel=channel,
                    name=skill_data["name"],
                    defaults={
                        "enabled": True,
                        "config": skill_data.get("config", {}),
                    },
                )

                status = "Created" if created else "Exists"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"    {status} skill: !{skill.name}"
                        f" in #{channel.twitch_channel_name}"
                    )
                )
