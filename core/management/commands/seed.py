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
                "config": {
                    "odds": 2,
                    "success": "$(user) - YOU GET YE FLASK! bardHype bardHype bardHype",
                    "failure": "You can't get ye flask, $(user)! bardPls",
                },
            },
        ]

        for cmd_data in spoonee_commands:
            cmd, created = BotCommand.objects.get_or_create(
                channel=channel,
                name=cmd_data["name"],
                defaults={
                    "type": cmd_data["type"],
                    "config": cmd_data["config"],
                    "created_by": "spoonee",
                },
            )

            status = "Created" if created else "Exists"
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
