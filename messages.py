"""Everything the bot says, in English and French.

Edit the wording here; the flow in app.py picks the text by the client's language.
- {name} is replaced with the client's chosen name (or "my dear" / "ma chérie").
- *bold* and _italic_ are WhatsApp formatting.
- Button titles must be 20 characters or fewer (WhatsApp limit).
- Medical facts (doses, timings, warning signs) must stay exactly as in the hotline's
  WHO-based protocol. Change the tone, not the facts.
The French texts use "tu" (warm, auntie-like). Have the team review them before going live.
"""

DEFAULT_NAME = {"en": "my dear", "fr": "ma chérie"}

MESSAGES = {
    # ----- Language, welcome, consent --------------------------------------
    "lang_prompt": {
        "en": (
            "Hello my dear 👋🏾 Welcome to *Aunty Queen*. I'm really glad you reached out.\n\n"
            "Which language is easier for you?\nQuelle langue préfères-tu ?"
        ),
        "fr": (
            "Hello my dear 👋🏾 Welcome to *Aunty Queen*. I'm really glad you reached out.\n\n"
            "Which language is easier for you?\nQuelle langue préfères-tu ?"
        ),
    },
    "consent": {
        "en": (
            "Thank you, my dear 💛 At Aunty Queen we talk openly about sexual and reproductive health, "
            "including safe abortion, using World Health Organization guidance. No judgement here, ever.\n\n"
            "🔒 *This chat is private.* What you share stays with our team and is only used to help you. "
            "If someone else can see your phone, you can turn on disappearing messages or delete this chat when we finish.\n\n"
            "To help you properly, I'll need to ask you a few personal questions. Is that alright with you?\n\n"
            "💡 _Tip: type *menu* at any time to change language, talk to a person, or start again._"
        ),
        "fr": (
            "Merci, ma chérie 💛 Chez Aunty Queen, nous parlons librement de santé sexuelle et reproductive, "
            "y compris de l'avortement sécurisé, selon les recommandations de l'Organisation mondiale de la Santé. "
            "Ici, personne ne te juge.\n\n"
            "🔒 *Cette conversation est privée.* Ce que tu partages reste avec notre équipe et sert uniquement à t'aider. "
            "Si quelqu'un d'autre peut voir ton téléphone, tu peux activer les messages éphémères ou supprimer la conversation à la fin.\n\n"
            "Pour bien t'aider, je vais te poser quelques questions personnelles. Ça te va ?\n\n"
            "💡 _Astuce : écris *menu* à tout moment pour changer de langue, parler à une personne ou recommencer._"
        ),
    },
    "consent_what": {
        "en": (
            "Of course! I'll ask about your age, the date of your last period, your schooling, "
            "how many pregnancies and children you've had, why you're reaching out, and whether someone is supporting you.\n\n"
            "You never have to answer anything you don't want to."
        ),
        "fr": (
            "Bien sûr ! Je vais te demander ton âge, la date de tes dernières règles, ton niveau d'études, "
            "le nombre de grossesses et d'enfants, pourquoi tu nous écris, et si quelqu'un te soutient.\n\n"
            "Tu n'es jamais obligée de répondre à une question."
        ),
    },
    "consent_thanks": {
        "en": "Thank you for trusting us 🙏🏾",
        "fr": "Merci de nous faire confiance 🙏🏾",
    },
    "name_ask": {
        "en": "What should I call you? Any name is fine, it doesn't have to be your real one 😊",
        "fr": "Comment veux-tu que je t'appelle ? N'importe quel prénom, pas forcément le vrai 😊",
    },

    # ----- A few details about her (script 1.3a + gender, city, how she heard) -----
    "demo_intro": {
        "en": (
            "Thank you, {name} 🌸 First, a few quick questions so we can serve women like you better. "
            "Type *skip* for any question you'd rather not answer.\n\n"
        ),
        "fr": (
            "Merci, {name} 🌸 D'abord, quelques petites questions pour mieux servir les femmes comme toi. "
            "Écris *passer* pour toute question à laquelle tu préfères ne pas répondre.\n\n"
        ),
    },
    "age": {
        "en": "What is your age range? Tap *Choose* to pick one.",
        "fr": "Quelle est ta tranche d'âge ? Appuie sur *Choisir* pour en sélectionner une.",
    },
    "gender": {
        "en": "How do you identify?",
        "fr": "Comment t'identifies-tu ?",
    },
    "city": {
        "en": "Which town or city do you live in?",
        "fr": "Dans quelle ville ou localité vis-tu ?",
    },
    "education": {
        "en": "What is the highest level of school you completed?",
        "fr": "Quel est le plus haut niveau d'études que tu as terminé ?",
    },
    "pregnancies": {
        "en": "How many times have you been pregnant, and how many children do you have? For example: *2 pregnancies, 1 child*",
        "fr": "Combien de fois as-tu été enceinte, et combien d'enfants as-tu ? Par exemple : *2 grossesses, 1 enfant*",
    },
    "heard": {
        "en": "Last one 😊 How did you hear about Aunty Queen?",
        "fr": "Dernière question 😊 Comment as-tu entendu parler d'Aunty Queen ?",
    },
    "heard_button": {
        "en": "Choose",
        "fr": "Choisir",
    },
    "welcome_back": {
        "en": "Welcome back, {name} 💛 It's good to hear from you again.",
        "fr": "Bon retour, {name} 💛 Ça fait plaisir de te relire.",
    },
    "opt_out_ack": {
        "en": "Done, we won't send you any more updates. You can still write to us any time 💛",
        "fr": "C'est noté, nous ne t'enverrons plus de nouvelles. Tu peux toujours nous écrire quand tu veux 💛",
    },

    # ----- How can we help ---------------------------------------------------
    "help_first": {
        "en": (
            "Lovely to meet you, {name} 🌸\n\n"
            "Tell me, how can Aunty Queen help you today? Just reply with the number:\n\n"
            "1️⃣ Safe abortion with pills\n"
            "2️⃣ I already took the pills and have questions\n"
            "3️⃣ Family planning / contraception\n"
            "4️⃣ Something else"
        ),
        "fr": (
            "Enchantée, {name} 🌸\n\n"
            "Dis-moi, comment Aunty Queen peut t'aider aujourd'hui ? Réponds simplement avec le numéro :\n\n"
            "1️⃣ L'avortement sécurisé avec des pilules\n"
            "2️⃣ J'ai déjà pris les pilules et j'ai des questions\n"
            "3️⃣ La contraception / planification familiale\n"
            "4️⃣ Autre chose"
        ),
    },
    "help_returning": {
        "en": (
            "How can Aunty Queen help you today? Just reply with the number:\n\n"
            "1️⃣ Safe abortion with pills\n"
            "2️⃣ I already took the pills and have questions\n"
            "3️⃣ Family planning / contraception\n"
            "4️⃣ Something else"
        ),
        "fr": (
            "Comment Aunty Queen peut t'aider aujourd'hui ? Réponds simplement avec le numéro :\n\n"
            "1️⃣ L'avortement sécurisé avec des pilules\n"
            "2️⃣ J'ai déjà pris les pilules et j'ai des questions\n"
            "3️⃣ La contraception / planification familiale\n"
            "4️⃣ Autre chose"
        ),
    },
    "help_again": {
        "en": (
            "No problem at all, {name}. Is there something else I can help you with? Reply with the number:\n\n"
            "1️⃣ Safe abortion with pills\n"
            "2️⃣ I already took the pills and have questions\n"
            "3️⃣ Family planning / contraception\n"
            "4️⃣ Something else"
        ),
        "fr": (
            "Pas de souci, {name}. Est-ce que je peux t'aider avec autre chose ? Réponds avec le numéro :\n\n"
            "1️⃣ L'avortement sécurisé avec des pilules\n"
            "2️⃣ J'ai déjà pris les pilules et j'ai des questions\n"
            "3️⃣ La contraception / planification familiale\n"
            "4️⃣ Autre chose"
        ),
    },
    "help_other": {
        "en": (
            "Of course, {name}. Tell me in your own words what's on your mind, "
            "and one of our counselors will answer you right here. Take your time 💛"
        ),
        "fr": (
            "Bien sûr, {name}. Raconte-moi avec tes propres mots ce qui te préoccupe, "
            "et une de nos conseillères va te répondre ici. Prends ton temps 💛"
        ),
    },
    "pills_offer": {
        "en": (
            "I'm here for you, {name}, and we'll go through this together.\n\n"
            "Aunty Queen shares trusted, scientific information about safe abortion with pills at home, "
            "for pregnancies up to 12 weeks. We can also tell you about MVA (manual vacuum aspiration), "
            "a short procedure done in a clinic.\n\n"
            "An abortion with pills works just like a miscarriage.\n\n"
            "Would you like me to explain safe abortion with pills?"
        ),
        "fr": (
            "Je suis là pour toi, {name}, et on va avancer ensemble.\n\n"
            "Aunty Queen partage des informations fiables et scientifiques sur l'avortement sécurisé avec des pilules à la maison, "
            "pour les grossesses jusqu'à 12 semaines. Nous pouvons aussi te parler de l'AMIU (aspiration manuelle intra-utérine), "
            "une courte intervention faite en clinique.\n\n"
            "Un avortement avec des pilules se passe comme une fausse couche.\n\n"
            "Veux-tu que je t'explique l'avortement sécurisé avec des pilules ?"
        ),
    },

    # ----- Her situation -------------------------------------------------------
    "confirmation": {
        "en": (
            "Let's start with a few questions so I can give you the right information 💛\n\n"
            "How did you find out you're pregnant, {name}?"
        ),
        "fr": (
            "Commençons par quelques questions pour que je puisse te donner les bonnes informations 💛\n\n"
            "Comment as-tu su que tu es enceinte, {name} ?"
        ),
    },
    "lmp_scan": {
        "en": (
            "Thank you. What did the scan say, how many weeks? And do you remember the first day of your last period? "
            "A rough date is perfectly fine 🗓️"
        ),
        "fr": (
            "Merci. Qu'a dit l'échographie, combien de semaines ? Et te souviens-tu du premier jour de tes dernières règles ? "
            "Une date approximative suffit 🗓️"
        ),
    },
    "lmp": {
        "en": "Thank you. Do you remember the first day of your last period? A rough date is perfectly fine 🗓️",
        "fr": "Merci. Te souviens-tu du premier jour de tes dernières règles ? Une date approximative suffit 🗓️",
    },
    "preference": {
        "en": (
            "Every woman is different. Some prefer to take pills at home, others prefer MVA, a short procedure in a clinic.\n\n"
            "Do you already have an idea which you'd prefer, {name}?"
        ),
        "fr": (
            "Chaque femme est différente. Certaines préfèrent prendre des pilules à la maison, "
            "d'autres préfèrent l'AMIU, une courte intervention en clinique.\n\n"
            "As-tu déjà une idée de ce que tu préfères, {name} ?"
        ),
    },
    "health": {
        "en": (
            "Now a few quick health questions, {name}:\n\n"
            "• Do you have any health problems or allergies?\n"
            "• Are you taking any medicine?\n"
            "• Do you have an IUD (coil)?"
        ),
        "fr": (
            "Maintenant, quelques petites questions sur ta santé, {name} :\n\n"
            "• As-tu des problèmes de santé ou des allergies ?\n"
            "• Prends-tu des médicaments ?\n"
            "• As-tu un stérilet (DIU) ?"
        ),
    },
    "health_yes": {
        "en": (
            "Thank you for telling me, that really helps. An early abortion with pills is safer than continuing a pregnancy "
            "and giving birth, and some health conditions can actually get worse during pregnancy.\n\n"
            "Women with health problems can still use the pills. We just advise having someone with you "
            "and being close to medical care, in case you need help."
        ),
        "fr": (
            "Merci de me le dire, ça m'aide beaucoup. Un avortement précoce avec des pilules est plus sûr que de poursuivre "
            "une grossesse et d'accoucher, et certaines maladies peuvent même s'aggraver pendant la grossesse.\n\n"
            "Les femmes qui ont des problèmes de santé peuvent quand même utiliser les pilules. Nous conseillons juste "
            "d'avoir quelqu'un avec soi et d'être proche d'un centre de soins, au cas où."
        ),
    },
    "health_details": {
        "en": "Can you tell me a little about the condition, the medicine, or the IUD?",
        "fr": "Peux-tu me parler un peu de ta maladie, de tes médicaments ou de ton stérilet ?",
    },
    "support": {
        "en": (
            "Complications are very rare, but it helps a lot to have someone by your side.\n\n"
            "Is there someone who can be with you during the abortion, or someone you can talk to about it, {name}?"
        ),
        "fr": (
            "Les complications sont très rares, mais ça aide beaucoup d'avoir quelqu'un à ses côtés.\n\n"
            "Y a-t-il quelqu'un qui peut être avec toi pendant l'avortement, ou à qui tu peux en parler, {name} ?"
        ),
    },
    "not_alone": {
        "en": "You are not alone, {name}. Aunty Queen is right here with you 💛\n\n",
        "fr": "Tu n'es pas seule, {name}. Aunty Queen est là avec toi 💛\n\n",
    },
    "decision": {
        "en": (
            "Before we go on, {name}: this decision is yours alone, without pressure from anyone. "
            "You know your life and your situation best, and whatever you choose, we respect it.\n\n"
            "Shall I go on and explain what you'll need?"
        ),
        "fr": (
            "Avant de continuer, {name} : cette décision t'appartient, sans pression de personne. "
            "Tu connais ta vie et ta situation mieux que quiconque, et quel que soit ton choix, nous le respectons.\n\n"
            "Je continue et je t'explique ce dont tu auras besoin ?"
        ),
    },
    "decision_questions": {
        "en": "Of course, {name}. Type your questions here and one of our counselors will answer you personally.",
        "fr": "Bien sûr, {name}. Écris tes questions ici et une de nos conseillères va te répondre personnellement.",
    },
    "decision_mva": {
        "en": "Thank you, {name}. One of our counselors will share information about MVA and clinics with you right here.",
        "fr": "Merci, {name}. Une de nos conseillères va te donner des informations sur l'AMIU et les cliniques, ici même.",
    },
    "methods": {
        "en": (
            "Here's what research shows works well. There are two safe methods:\n\n"
            "1️⃣ *Mifepristone + misoprostol*: 1 mifepristone tablet (200 mg) and 4 misoprostol tablets (200 mcg each)\n"
            "2️⃣ *Misoprostol alone*: 12 misoprostol tablets (200 mcg each)\n\n"
            "Where to get the pills: a counselor can talk with you privately about safe options."
        ),
        "fr": (
            "Voici ce que la recherche montre comme efficace. Il existe deux méthodes sûres :\n\n"
            "1️⃣ *Mifépristone + misoprostol* : 1 comprimé de mifépristone (200 mg) et 4 comprimés de misoprostol (200 mcg chacun)\n"
            "2️⃣ *Misoprostol seul* : 12 comprimés de misoprostol (200 mcg chacun)\n\n"
            "Où trouver les pilules : une conseillère peut en parler avec toi en toute confidentialité."
        ),
    },

    # ----- Before and during -------------------------------------------------
    "plan": {
        "en": (
            "While you get the pills, let's make a little plan for the day 📝\n\n"
            "• Someone to support you emotionally\n"
            "• Childcare and other tasks taken care of\n"
            "• A calm, private place, ideally with your own bathroom\n"
            "• Painkillers like ibuprofen 400–600 mg ready in advance\n"
            "• An idea of where you would go if you needed extra care\n\n"
            "Any questions so far?"
        ),
        "fr": (
            "Pendant que tu te procures les pilules, préparons un petit plan pour le jour J 📝\n\n"
            "• Quelqu'un pour te soutenir moralement\n"
            "• La garde des enfants et les autres tâches organisées\n"
            "• Un endroit calme et privé, idéalement avec des toilettes à toi\n"
            "• Des antidouleurs comme l'ibuprofène 400–600 mg prêts à l'avance\n"
            "• Une idée de l'endroit où aller si tu as besoin de soins\n\n"
            "Des questions jusqu'ici ?"
        ),
    },
    "plan_ask": {
        "en": "Go ahead, {name}, type your question 💬",
        "fr": "Vas-y, {name}, écris ta question 💬",
    },
    "plan_question_reask": {
        "en": "Type your question, or write *ready* when you want to continue.",
        "fr": "Écris ta question, ou écris *prête* quand tu veux continuer.",
    },
    "plan_question_human": {
        "en": "Thank you. One of our counselors will answer your question right here.",
        "fr": "Merci. Une de nos conseillères va répondre à ta question ici.",
    },
    "method": {
        "en": (
            "Next I'll explain exactly how to take the pills. It helps to have a pen and paper to write the steps down ✍🏾\n\n"
            "Which pills will you be using?"
        ),
        "fr": (
            "Je vais maintenant t'expliquer exactement comment prendre les pilules. "
            "Ça aide d'avoir un stylo et du papier pour noter les étapes ✍🏾\n\n"
            "Quelles pilules vas-tu utiliser ?"
        ),
    },
    "steps_combo": {
        "en": (
            "*How to take mifepristone + misoprostol (1 + 4 pills):*\n\n"
            "*Step 1:* Swallow 1 mifepristone tablet (200 mg) with a glass of water.\n\n"
            "*Step 2:* 24 hours later, place 4 misoprostol tablets (200 mcg each) between your gum and cheek, "
            "2 on the left and 2 on the right. Leave them for 30 minutes to dissolve, then swallow whatever is left."
        ),
        "fr": (
            "*Comment prendre mifépristone + misoprostol (1 + 4 pilules) :*\n\n"
            "*Étape 1 :* Avale 1 comprimé de mifépristone (200 mg) avec un verre d'eau.\n\n"
            "*Étape 2 :* 24 heures plus tard, place 4 comprimés de misoprostol (200 mcg chacun) entre la gencive et la joue, "
            "2 à gauche et 2 à droite. Laisse-les fondre pendant 30 minutes, puis avale ce qui reste."
        ),
    },
    "steps_miso": {
        "en": (
            "*How to take misoprostol alone (12 pills in total):*\n"
            "The most effective way is 4 pills under the tongue every 3 hours, 3 times.\n\n"
            "*Step 1:* Put 4 pills under your tongue. Don't swallow for 30 minutes while they dissolve, then swallow what's left.\n"
            "*Step 2:* 3 hours later, put another 4 pills under your tongue for 30 minutes.\n"
            "*Step 3:* 3 hours later, put the last 4 pills under your tongue for 30 minutes."
        ),
        "fr": (
            "*Comment prendre le misoprostol seul (12 pilules au total) :*\n"
            "La façon la plus efficace : 4 pilules sous la langue toutes les 3 heures, 3 fois.\n\n"
            "*Étape 1 :* Mets 4 pilules sous la langue. N'avale pas pendant 30 minutes, le temps qu'elles fondent, puis avale ce qui reste.\n"
            "*Étape 2 :* 3 heures plus tard, mets encore 4 pilules sous la langue pendant 30 minutes.\n"
            "*Étape 3 :* 3 heures plus tard, mets les 4 dernières pilules sous la langue pendant 30 minutes."
        ),
    },
    "good_to_know": {
        "en": (
            "📌 *Good to know:*\n"
            "• Don't eat or drink during the 30 minutes while the pills dissolve. Before and after, you can eat and drink normally.\n"
            "• Normal side effects: cramps, chills, a mild fever, nausea, diarrhoea.\n"
            "• Bleeding usually starts 2 to 4 hours after the misoprostol. The heaviest bleeding, with clots, lasts 1 to 4 hours and then eases.\n"
            "• For pain: you can take ibuprofen 600 mg after the first misoprostol dose."
        ),
        "fr": (
            "📌 *Bon à savoir :*\n"
            "• Ne mange pas et ne bois pas pendant les 30 minutes où les pilules fondent. Avant et après, tu peux manger et boire normalement.\n"
            "• Effets normaux : crampes, frissons, légère fièvre, nausées, diarrhée.\n"
            "• Les saignements commencent en général 2 à 4 heures après le misoprostol. Les plus forts, avec des caillots, durent 1 à 4 heures puis diminuent.\n"
            "• Contre la douleur : tu peux prendre de l'ibuprofène 600 mg après la première dose de misoprostol."
        ),
    },
    "understanding": {
        "en": "Can you tell me in your own words how you'll take the pills? Is anything unclear? 🤔",
        "fr": "Peux-tu me redire avec tes mots comment tu vas prendre les pilules ? Y a-t-il quelque chose qui n'est pas clair ? 🤔",
    },

    # ----- Warning signs -------------------------------------------------------
    "warning_intro": {
        "en": "Thank you, {name}, well done 👏🏾 Now, here are the *4 warning signs* to always remember:",
        "fr": "Merci, {name}, bravo 👏🏾 Maintenant, voici les *4 signes d'alerte* à toujours retenir :",
    },
    "warning_again": {
        "en": "Of course, here they are again, {name}:",
        "fr": "Bien sûr, les revoici, {name} :",
    },
    "warning_signs": {
        "en": (
            "1️⃣ *Too much bleeding*: soaking more than 2 maxi pads an hour for 2 or 3 hours in a row, or bleeding like an open tap.\n"
            "2️⃣ *Severe pain* that painkillers don't relieve.\n"
            "3️⃣ *Bad-smelling* discharge from the vagina.\n"
            "4️⃣ *Fever* over 38°C for more than 24 hours, or over 39°C at any time.\n\n"
            "🏥 *Getting care:* any complication is treated exactly like a miscarriage. "
            "You can go to any clinic and simply say you had a miscarriage.\n\n"
            "Are these 4 signs clear to you?"
        ),
        "fr": (
            "1️⃣ *Trop de saignements* : tremper plus de 2 grandes serviettes par heure pendant 2 ou 3 heures de suite, ou saigner comme un robinet ouvert.\n"
            "2️⃣ *Une douleur forte* que les antidouleurs ne calment pas.\n"
            "3️⃣ Des pertes vaginales qui *sentent mauvais*.\n"
            "4️⃣ *Une fièvre* de plus de 38°C pendant plus de 24 heures, ou de plus de 39°C à tout moment.\n\n"
            "🏥 *Se faire soigner :* toute complication se soigne exactement comme une fausse couche. "
            "Tu peux aller dans n'importe quelle clinique et dire simplement que tu as fait une fausse couche.\n\n"
            "Ces 4 signes sont-ils clairs pour toi ?"
        ),
    },

    # ----- After ----------------------------------------------------------------
    "after": {
        "en": (
            "📌 *After the abortion:*\n"
            "• Bleeding slowly gets lighter and can last 1 to 3 weeks.\n"
            "• Your period usually comes back in 4 to 6 weeks.\n"
            "• For the first 2 to 3 days, don't put anything in the vagina: no sex, no tampons, no baths.\n"
            "• To be sure it worked, take a pregnancy test 3 to 4 weeks later (a test done earlier can still show positive).\n\n"
            "You can get pregnant again very soon after an abortion. Would you like information about contraception?"
        ),
        "fr": (
            "📌 *Après l'avortement :*\n"
            "• Les saignements diminuent petit à petit et peuvent durer 1 à 3 semaines.\n"
            "• Les règles reviennent en général après 4 à 6 semaines.\n"
            "• Pendant les 2 à 3 premiers jours, ne mets rien dans le vagin : pas de rapports, pas de tampons, pas de bains.\n"
            "• Pour être sûre que ça a marché, fais un test de grossesse 3 à 4 semaines après (un test fait plus tôt peut encore être positif).\n\n"
            "Tu peux retomber enceinte très vite après un avortement. Veux-tu des informations sur la contraception ?"
        ),
    },
    "contraception_info": {
        "en": (
            "*Contraception options:*\n\n"
            "• *Pill, patch, injection, implant*: can be started up to 5 days after the misoprostol, and protect you straight away.\n"
            "• *Vaginal ring*: can be inserted as soon as 2 or 3 days after the misoprostol.\n"
            "• *IUD (coil)*: inserted once the abortion is confirmed complete, or during your next period.\n"
            "• *Condoms and other barrier methods*: from the first time you have sex again.\n"
            "• *Fertility awareness*: once your cycles are regular again."
        ),
        "fr": (
            "*Les méthodes de contraception :*\n\n"
            "• *Pilule, patch, injection, implant* : peuvent être commencés jusqu'à 5 jours après le misoprostol, et protègent tout de suite.\n"
            "• *Anneau vaginal* : peut être mis dès 2 ou 3 jours après le misoprostol.\n"
            "• *Stérilet (DIU)* : posé une fois l'avortement confirmé complet, ou pendant les prochaines règles.\n"
            "• *Préservatifs et autres méthodes barrières* : dès la reprise des rapports.\n"
            "• *Méthodes naturelles* : une fois que les cycles sont redevenus réguliers."
        ),
    },
    "followup": {
        "en": (
            "Is there anything else on your mind, {name}? 💭\n\n"
            "Would you like us to check on you later? If yes, tell me which day and time it's safe to message you."
        ),
        "fr": (
            "Y a-t-il autre chose qui te préoccupe, {name} ? 💭\n\n"
            "Veux-tu qu'on prenne de tes nouvelles plus tard ? Si oui, dis-moi quel jour et à quelle heure on peut t'écrire sans risque."
        ),
    },
    "closing": {
        "en": (
            "Thank you, {name}, I've noted that 🙏🏾\n\n"
            "Remember, you can write to Aunty Queen any time you have a question or a worry. We're always here for you. "
            "Take good care of yourself 💛\n\n"
            "_One of our counselors is also here if you'd like to talk to a person._"
        ),
        "fr": (
            "Merci, {name}, c'est noté 🙏🏾\n\n"
            "N'oublie pas : tu peux écrire à Aunty Queen à tout moment si tu as une question ou une inquiétude. "
            "Nous sommes toujours là pour toi. Prends bien soin de toi 💛\n\n"
            "_Une de nos conseillères est aussi là si tu veux parler à une personne._"
        ),
    },

    # ----- Already used the pills ----------------------------------------------
    "triage": {
        "en": (
            "{name}, I want to make sure you're safe. Do you have any of these 4 warning signs right now?\n\n"
            "1️⃣ Soaking 2 or more pads an hour, for 2 hours\n"
            "2️⃣ Severe pain that painkillers don't relieve\n"
            "3️⃣ Bad-smelling discharge from the vagina\n"
            "4️⃣ Fever over 38°C"
        ),
        "fr": (
            "{name}, je veux m'assurer que tu vas bien. As-tu un de ces 4 signes d'alerte en ce moment ?\n\n"
            "1️⃣ Tu trempes 2 serviettes ou plus par heure, pendant 2 heures\n"
            "2️⃣ Une douleur forte que les antidouleurs ne calment pas\n"
            "3️⃣ Des pertes vaginales qui sentent mauvais\n"
            "4️⃣ Une fièvre de plus de 38°C"
        ),
    },
    "triage_no": {
        "en": "Thank you for letting me know, {name}. One of our counselors will go through your symptoms with you right here.",
        "fr": "Merci de me le dire, {name}. Une de nos conseillères va regarder tes symptômes avec toi, ici même.",
    },
    "urgent": {
        "en": (
            "🚨 *What you're describing is a sign that you need medical care.*\n\n"
            "Please go to the nearest health facility now. The treatment is the same as for a miscarriage, "
            "and you can simply say you had a miscarriage. Message us when you can, we're right here 💛"
        ),
        "fr": (
            "🚨 *Ce que tu décris est un signe qu'il te faut des soins médicaux.*\n\n"
            "Va s'il te plaît au centre de santé le plus proche maintenant. Le traitement est le même que pour une fausse couche, "
            "et tu peux simplement dire que tu as fait une fausse couche. Écris-nous dès que tu peux, nous sommes là 💛"
        ),
    },

    # ----- General ------------------------------------------------------------------
    "human_handover": {
        "en": "Thank you. One of our counselors will reply to you right here 💛",
        "fr": "Merci. Une de nos conseillères va te répondre ici 💛",
    },
    "ai_limit": {
        "en": "One of our counselors will continue with you right here 💛",
        "fr": "Une de nos conseillères va continuer avec toi ici 💛",
    },
    "back_to_question": {
        "en": "↩️ Now, let's pick up where we were:",
        "fr": "↩️ Bon, reprenons là où nous en étions :",
    },
    "qa_check": {
        "en": "Did that answer your question, {name}? 💛",
        "fr": "Est-ce que ça répond à ta question, {name} ? 💛",
    },
    "ai_unavailable": {
        "en": "That's a good question, {name}. A counselor will answer it for you here shortly 💛 Meanwhile, let's continue:",
        "fr": "C'est une bonne question, {name}. Une conseillère va te répondre ici très bientôt 💛 En attendant, continuons :",
    },
    "qa_go_ahead": {
        "en": "Of course, go ahead and type your question 💬",
        "fr": "Bien sûr, écris ta question 💬",
    },
    "menu": {
        "en": (
            "Here's what I can do for you, {name} 💛\n\n"
            "Choose an option below, or just type your answer to carry on where we were."
        ),
        "fr": (
            "Voici ce que je peux faire pour toi, {name} 💛\n\n"
            "Choisis une option ci-dessous, ou écris simplement ta réponse pour continuer là où nous en étions."
        ),
    },
    "pick_language": {
        "en": "Which language would you like?\nQuelle langue préfères-tu ?",
        "fr": "Which language would you like?\nQuelle langue préfères-tu ?",
    },
    "language_switched": {
        "en": "No problem, we'll continue in English 😊",
        "fr": "Pas de souci, on continue en français 😊",
    },
    "restarting": {
        "en": "Of course, let's start again from the beginning 🌸",
        "fr": "Bien sûr, recommençons depuis le début 🌸",
    },
    "not_understood": {
        "en": "Sorry my dear, I didn't quite get that. Could you pick one of the options below?",
        "fr": "Pardon ma chérie, je n'ai pas bien compris. Peux-tu choisir une des options ci-dessous ?",
    },
    "typed_only": {
        "en": (
            "Sorry, I can only read typed messages for now. Please type your answer, "
            "or wait a little and a counselor will reply to you here 💛"
        ),
        "fr": (
            "Désolée, pour l'instant je ne peux lire que les messages écrits. Écris ta réponse, "
            "ou patiente un peu et une conseillère va te répondre ici 💛"
        ),
    },
    "delete_ack": {
        "en": "We've received your request. A counselor will delete your records and confirm with you here.",
        "fr": "Nous avons bien reçu ta demande. Une conseillère va supprimer tes informations et te le confirmer ici.",
    },
}

# Button labels shown to the client (max 20 characters). The English option titles in
# app.py STEPS are what gets saved to the Google Sheet, so the data stays in one language.
BUTTONS = {
    "lang_en": {"en": "English", "fr": "English"},
    "lang_fr": {"en": "Français", "fr": "Français"},
    "c_ok": {"en": "Yes, that's fine", "fr": "Oui, ça me va"},
    "c_what": {"en": "What will you ask?", "fr": "Quelles questions ?"},
    "pills_yes": {"en": "Yes, please", "fr": "Oui, s'il te plaît"},
    "pills_no": {"en": "Not now", "fr": "Pas maintenant"},
    "conf_test": {"en": "Pregnancy test", "fr": "Test de grossesse"},
    "conf_scan": {"en": "Ultrasound scan", "fr": "Échographie"},
    "conf_missed": {"en": "My period is late", "fr": "Règles en retard"},
    "pref_pills": {"en": "Pills at home", "fr": "Pilules à la maison"},
    "pref_mva": {"en": "MVA in a clinic", "fr": "AMIU en clinique"},
    "pref_both": {"en": "Tell me about both", "fr": "Les deux, explique"},
    "health_no": {"en": "No, none of these", "fr": "Non, aucun"},
    "health_yes": {"en": "Yes, some of these", "fr": "Oui, j'en ai"},
    "supp_yes": {"en": "Yes, I have someone", "fr": "Oui, j'ai quelqu'un"},
    "supp_no": {"en": "No, I'm alone", "fr": "Non, je suis seule"},
    "dec_continue": {"en": "Yes, go on", "fr": "Oui, continue"},
    "dec_questions": {"en": "I have questions", "fr": "J'ai des questions"},
    "plan_ready": {"en": "Ready for the steps", "fr": "Prête pour la suite"},
    "plan_ask": {"en": "I have a question", "fr": "J'ai une question"},
    "m_miso_only": {"en": "Misoprostol alone", "fr": "Misoprostol seul"},
    "m_combo": {"en": "Mife + Misoprostol", "fr": "Mife + Misoprostol"},
    "warn_clear": {"en": "Yes, all clear", "fr": "Oui, c'est clair"},
    "warn_repeat": {"en": "Please repeat", "fr": "Peux-tu répéter ?"},
    "contra_yes": {"en": "Yes, please", "fr": "Oui, s'il te plaît"},
    "contra_no": {"en": "No, thank you", "fr": "Non, merci"},
    "warn_report_yes": {"en": "Yes, I do", "fr": "Oui"},
    "warn_report_no": {"en": "No, I don't", "fr": "Non"},
    "gen_woman": {"en": "Woman", "fr": "Femme"},
    "gen_man": {"en": "Man", "fr": "Homme"},
    "gen_other": {"en": "Other / rather not", "fr": "Autre / sans réponse"},
    "edu_primary": {"en": "None or primary", "fr": "Aucun ou primaire"},
    "edu_secondary": {"en": "Secondary", "fr": "Secondaire"},
    "edu_higher": {"en": "University / higher", "fr": "Université"},
    # List rows (max 24 characters)
    "age_u18": {"en": "Under 18", "fr": "Moins de 18 ans"},
    "age_18_24": {"en": "18-24", "fr": "18-24 ans"},
    "age_25_34": {"en": "25-34", "fr": "25-34 ans"},
    "age_35_44": {"en": "35-44", "fr": "35-44 ans"},
    "age_45": {"en": "45 or older", "fr": "45 ans ou plus"},
    "heard_friend": {"en": "Friend or family", "fr": "Ami(e) ou famille"},
    "heard_social": {"en": "Social media", "fr": "Réseaux sociaux"},
    "heard_radio": {"en": "Radio or TV", "fr": "Radio ou télé"},
    "heard_web": {"en": "Website", "fr": "Site internet"},
    "heard_health": {"en": "Health worker / clinic", "fr": "Agent de santé"},
    "heard_other": {"en": "Other", "fr": "Autre"},
    "qa_continue": {"en": "Yes, let's continue", "fr": "Oui, on continue"},
    "qa_more": {"en": "Another question", "fr": "Une autre question"},
    # Menu (works at any step)
    "g_lang": {"en": "🌍 Change language", "fr": "🌍 Changer de langue"},
    "g_human": {"en": "Talk to a person", "fr": "Parler à quelqu'un"},
    "g_restart": {"en": "🔄 Start again", "fr": "🔄 Recommencer"},
    "g_en": {"en": "English", "fr": "English"},
    "g_fr": {"en": "Français", "fr": "Français"},
}
