"""Hand-written TRAINING rows in Malayalam script and Manglish (Malayalam in English letters).

Why this file exists: the first fine-tune scored English 0.97 but Malayalam 0.21 and Manglish 0.25, because the
Malayalam training text was written by a language model and some of it was nonsense. These rows are written by a
person, kept SEPARATE from the held-out test set in handwritten.py (prepare_data.py refuses to build if any text is
in both), and repeated in training (UPSAMPLE) so the English rows don't drown them.

TRAIN: (text, urgency, specialist, lang). An English gloss follows each Malayalam / Manglish line as a comment so a
reviewer can check the label. Add more rows here and rerun ml/prepare_data.py. More real wording is the best way to improve.
"""

UPSAMPLE = 4

TRAIN = [
    # ================= Malayalam script =================
    # ---- emergency
    ("നെഞ്ചിൽ കനത്ത വേദന, ഇടത് കൈയിലേക്ക് പടരുന്നു", "emergency", "cardiologist", "ml"),  # heavy chest pain spreading to left arm
    ("നെഞ്ച് വേദനിക്കുന്നു, ശരീരം വിയർത്തു കുളിച്ചു", "emergency", "cardiologist", "ml"),  # chest hurts, drenched in sweat
    ("ശ്വാസം എടുക്കാൻ പറ്റുന്നില്ല, ചുണ്ട് നീലിച്ചു", "emergency", "pulmonologist", "ml"),  # cannot breathe, lips turned blue
    ("അമ്മയ്ക്ക് ശ്വാസം കിട്ടുന്നില്ല, വല്ലാതെ കിതയ്ക്കുന്നു", "emergency", "pulmonologist", "ml"),  # mother cannot get breath, gasping
    ("അമ്മൂമ്മ കുഴഞ്ഞു വീണു, വിളിച്ചാൽ മിണ്ടുന്നില്ല", "emergency", "general_physician", "ml"),  # grandmother collapsed, not responding when called
    ("ഭർത്താവിന് പെട്ടെന്ന് ബോധം പോയി", "emergency", "general_physician", "ml"),  # husband suddenly lost consciousness
    ("വായ ഒരു വശത്തേക്ക് കോടി, കൈ അനക്കാൻ പറ്റുന്നില്ല", "emergency", "neurologist", "ml"),  # mouth twisted to one side, cannot move arm
    ("പെട്ടെന്ന് സംസാരിക്കാൻ പറ്റാതായി, ഒരു വശം തളർന്നു", "emergency", "neurologist", "ml"),  # suddenly cannot speak, one side weak
    ("മുറിവിൽ നിന്ന് ചോര നിൽക്കുന്നില്ല, തുണി മുഴുവൻ നനഞ്ഞു", "emergency", "general_physician", "ml"),  # wound not stopping bleeding, cloth soaked
    ("ഛർദ്ദിയിൽ ചോര കണ്ടു, തല കറങ്ങുന്നു", "emergency", "gastroenterologist", "ml"),  # blood in vomit, dizzy
    ("കുഞ്ഞിന് ഫിറ്റ്സ് വന്നു, അഞ്ച് മിനിറ്റായി നിൽക്കുന്നില്ല", "emergency", "paediatrician", "ml"),  # child seizure, not stopping for 5 minutes
    ("ഇഞ്ചക്ഷൻ എടുത്ത ഉടനെ മുഖം വീർത്തു, ശ്വാസം മുട്ടി", "emergency", "general_physician", "ml"),  # face swelled right after injection, breathless
    ("ഷുഗർ 40, വിറയലും വിയർപ്പും, മിണ്ടുന്നില്ല", "emergency", "diabetologist", "ml"),  # sugar 40, shaking, sweating, unresponsive
    ("ജീവിതം അവസാനിപ്പിക്കണം എന്ന് തോന്നുന്നു", "emergency", "psychiatrist", "ml"),  # feel like ending my life
    # ---- urgent
    ("രണ്ട് ദിവസമായി 102 പനി, ഒട്ടും കുറയുന്നില്ല", "urgent", "general_physician", "ml"),  # fever 102 for two days, not coming down
    ("കുഞ്ഞിന് പനിയും ഛർദ്ദിയും, പാൽ കുടിക്കുന്നില്ല", "urgent", "paediatrician", "ml"),  # child fever and vomiting, not feeding
    ("വയറ് വേദന കഠിനം, വലത് വശത്ത് താഴെ", "urgent", "gastroenterologist", "ml"),  # severe abdominal pain, lower right
    ("മൂത്രം ഒഴിക്കുമ്പോൾ ചോരയും കടുത്ത വേദനയും", "urgent", "urologist", "ml"),  # blood and severe pain while passing urine
    ("ബിപി 200, തല പൊട്ടുന്ന പോലെ വേദന", "urgent", "cardiologist", "ml"),  # BP 200, head feels like bursting
    ("ഷുഗർ 420, ദാഹവും ക്ഷീണവും ഉണ്ട്", "urgent", "diabetologist", "ml"),  # sugar 420, thirst and tiredness
    ("ചെവിയിൽ നിന്ന് പഴുപ്പ് വരുന്നു, കടുത്ത വേദന", "urgent", "ent", "ml"),  # pus from ear, severe pain
    ("പെട്ടെന്ന് ഒരു കണ്ണ് ചുവന്ന് കാഴ്ച കുറഞ്ഞു", "urgent", "ophthalmologist", "ml"),  # one eye suddenly red, vision reduced
    ("വീണു, കാൽ നീര് വച്ച് നിൽക്കാൻ വയ്യ", "urgent", "orthopaedician", "ml"),  # fell, leg swollen, cannot stand
    ("ചുമയും പനിയും ശ്വാസംമുട്ടലും അഞ്ച് ദിവസമായി", "urgent", "pulmonologist", "ml"),  # cough, fever, breathlessness for five days
    ("ഗർഭിണിയാണ്, വയറ്റിൽ കടുത്ത വേദനയും രക്തസ്രാവവും", "urgent", "gynaecologist", "ml"),  # pregnant, severe stomach pain and bleeding
    # ---- routine
    ("കാൽമുട്ടിൽ വേദന, കുറച്ച് ആഴ്ചയായി", "routine", "orthopaedician", "ml"),  # knee pain for some weeks
    ("നടുവേദന മാസങ്ങളായി, ഇരുന്നാൽ കൂടും", "routine", "orthopaedician", "ml"),  # back pain for months, worse when sitting
    ("ഷുഗർ പരിശോധനയ്ക്ക് സമയമായി", "routine", "diabetologist", "ml"),  # due for sugar check
    ("പ്രമേഹത്തിന്റെ മരുന്ന് വാങ്ങണം, ഡോക്ടറെ കാണണം", "routine", "diabetologist", "ml"),  # need diabetes medicine, want to see doctor
    ("ബിപി ടാബ്‌ലെറ്റ് കഴിഞ്ഞു, പരിശോധിക്കണം", "routine", "cardiologist", "ml"),  # BP tablets finished, need check
    ("തലവേദന ഇടയ്ക്കിടെ വരുന്നു, ആഴ്ചകളായി", "routine", "neurologist", "ml"),  # headaches coming on and off for weeks
    ("മുഖത്ത് മുഖക്കുരു കൂടുതലായി", "routine", "dermatologist", "ml"),  # more pimples on face
    ("മുടി കൊഴിച്ചിൽ കൂടുന്നു", "routine", "dermatologist", "ml"),  # hair fall increasing
    ("ഗ്യാസും പുളിച്ചു തികട്ടലും ഭക്ഷണത്തിന് ശേഷം", "routine", "gastroenterologist", "ml"),  # gas and acid reflux after food
    ("പല്ലിൽ പുളിപ്പും ചെറിയ വേദനയും", "routine", "dentist", "ml"),  # tooth sensitivity and mild pain
    ("ഉറക്കം വരുന്നില്ല, മനസ്സിന് സമാധാനമില്ല", "routine", "psychiatrist", "ml"),  # cannot sleep, mind not at peace
    ("തൈറോയ്ഡ് പരിശോധിക്കാൻ വന്നതാണ്", "routine", "general_physician", "ml"),  # came to check thyroid
    ("മൂക്കടപ്പും തുമ്മലും ഒരാഴ്ചയായി", "routine", "ent", "ml"),  # blocked nose and sneezing for a week
    ("പൊതുവായ ഒരു ചെക്കപ്പ് വേണം", "routine", "general_physician", "ml"),  # want a general checkup
    # ---- self care
    ("ചെറിയ തൊണ്ടവേദന, ഇന്ന് തുടങ്ങിയതാണ്", "self_care", "ent", "ml"),  # mild sore throat, started today
    ("ഇന്ന് ചെറിയ ക്ഷീണം മാത്രം", "self_care", "general_physician", "ml"),  # just slightly tired today
    ("കൈയിൽ ചെറിയ പൊള്ളൽ, ഇപ്പോൾ കുഴപ്പമില്ല", "self_care", "dermatologist", "ml"),  # small burn on hand, fine now
    ("വയറ്റിൽ ചെറിയ ഗ്യാസ്", "self_care", "gastroenterologist", "ml"),  # a bit of gas in stomach
    ("കാൽ ചെറുതായി കടയുന്നു, നടന്നതിന് ശേഷം", "self_care", "orthopaedician", "ml"),  # leg a little sore after walking
    ("നേരിയ ചുമ, പനി ഇല്ല", "self_care", "general_physician", "ml"),  # slight cough, no fever
    # ================= Manglish =================
    # ---- emergency
    ("nenjil kanatha vedana, idath kayyilekku padarunnu", "emergency", "cardiologist", "ml-latin"),  # heavy chest pain spreading to left arm
    ("nenju vedanikkunnu, vallathe viyarkkunnu", "emergency", "cardiologist", "ml-latin"),  # chest hurts, sweating a lot
    ("shwasam edukkan pattunnilla, chundu neelichu", "emergency", "pulmonologist", "ml-latin"),  # cannot breathe, lips blue
    ("ammakku shwasam kittunnilla, kithakkunnu", "emergency", "pulmonologist", "ml-latin"),  # mother cannot get breath, gasping
    ("ammamma kuzhanju veenu, vilichaal mindunnilla", "emergency", "general_physician", "ml-latin"),  # grandmother collapsed, not responding
    ("bodham poyi, veenu poyi", "emergency", "general_physician", "ml-latin"),  # lost consciousness and fell
    ("vaayi oru vashathekku kodi, kai anakkan pattunnilla", "emergency", "neurologist", "ml-latin"),  # mouth twisted, cannot move arm
    ("pettennu samsarikkan pattathayi, oru vasham thalarnnu", "emergency", "neurologist", "ml-latin"),  # suddenly cannot speak, one side weak
    ("murivil ninnu chora nilkkunnilla", "emergency", "general_physician", "ml-latin"),  # wound bleeding not stopping
    ("chardhiyil chora kandu, thala karangunnu", "emergency", "gastroenterologist", "ml-latin"),  # blood in vomit, dizzy
    ("kunjinu fits vannu, nilkkunnilla", "emergency", "paediatrician", "ml-latin"),  # child seizure not stopping
    ("injection eduthappol mukham veernnu, shwasam muttunnu", "emergency", "general_physician", "ml-latin"),  # face swelled after injection, breathless
    ("sugar 40, viraykkunnu, mindunnilla", "emergency", "diabetologist", "ml-latin"),  # sugar 40, shaking, unresponsive
    ("jeevitham avasanippikkanam ennu thonnunnu", "emergency", "psychiatrist", "ml-latin"),  # feel like ending my life
    # ---- urgent
    ("randu divasam aayi 102 pani, kurayunnilla", "urgent", "general_physician", "ml-latin"),  # fever 102 two days not reducing
    ("kunjinu pani und, chardhiyum, paal kudikkunnilla", "urgent", "paediatrician", "ml-latin"),  # child fever and vomiting, not feeding
    ("vayaru vedana kadinam, valathu vashathu thaazhe", "urgent", "gastroenterologist", "ml-latin"),  # severe stomach pain lower right
    ("moothram ozhikkumbol chorayum vedanayum", "urgent", "urologist", "ml-latin"),  # blood and pain while urinating
    ("bp 200, thala pottunna pole vedana", "urgent", "cardiologist", "ml-latin"),  # BP 200, head bursting pain
    ("sugar 420, daham und, ksheenam und", "urgent", "diabetologist", "ml-latin"),  # sugar 420, thirst, tiredness
    ("cheviyil ninnu pazhuppu varunnu, vedana und", "urgent", "ent", "ml-latin"),  # pus from ear, pain
    ("oru kannu pettennu chuvannu, kazhcha kuranju", "urgent", "ophthalmologist", "ml-latin"),  # one eye suddenly red, vision dropped
    ("veenu, kaal neeru vechu, nilkkan vayya", "urgent", "orthopaedician", "ml-latin"),  # fell, leg swollen, cannot stand
    ("chuma, pani, shwasam muttal anchu divasam aayi", "urgent", "pulmonologist", "ml-latin"),  # cough fever breathlessness five days
    ("garbhini aanu, vayattil vedanayum raktha sravavum", "urgent", "gynaecologist", "ml-latin"),  # pregnant, belly pain and bleeding
    # ---- routine
    ("kalmuttil vedana, kurachu aazhcha aayi", "routine", "orthopaedician", "ml-latin"),  # knee pain for a few weeks
    ("naduvedana masangalaayi, irunnaal koodum", "routine", "orthopaedician", "ml-latin"),  # back pain for months
    ("sugar pariksha cheyyan samayam aayi", "routine", "diabetologist", "ml-latin"),  # due for sugar test
    ("prameham marunnu vaangaanam, doctore kaananam", "routine", "diabetologist", "ml-latin"),  # need diabetes medicine, see doctor
    ("bp tablet kazhinju, pariksha cheyyanam", "routine", "cardiologist", "ml-latin"),  # BP tablets finished, need check
    ("thalavedana idakkide varunnu, aazhchakalaayi", "routine", "neurologist", "ml-latin"),  # headaches on and off for weeks
    ("mukhathu mukhakkuru koodi", "routine", "dermatologist", "ml-latin"),  # more pimples
    ("mudi kozhichil koodunnu", "routine", "dermatologist", "ml-latin"),  # hair fall increasing
    ("gas und, bhakshanam kazhinjaal pulichu thikattal", "routine", "gastroenterologist", "ml-latin"),  # gas and reflux after food
    ("pallil pulippum cheriya vedanayum", "routine", "dentist", "ml-latin"),  # tooth sensitivity and mild pain
    ("urakkam varunnilla, manassinu samadhanam illa", "routine", "psychiatrist", "ml-latin"),  # cannot sleep, no peace of mind
    ("thyroid pariksha cheyyan vannathaanu", "routine", "general_physician", "ml-latin"),  # came for thyroid test
    ("mookkadappum thummalum oru aazhcha aayi", "routine", "ent", "ml-latin"),  # blocked nose and sneezing a week
    ("pothuvaaya oru checkup venam", "routine", "general_physician", "ml-latin"),  # want a general checkup
    # ---- self care
    ("cheriya thondavedana, innu thudangiyathaanu", "self_care", "ent", "ml-latin"),  # mild sore throat since today
    ("innu cheriya ksheenam maathram", "self_care", "general_physician", "ml-latin"),  # slightly tired today
    ("kayyil cheriya pollal, ippo kuzhappamilla", "self_care", "dermatologist", "ml-latin"),  # small burn, fine now
    ("vayattil cheriya gas", "self_care", "gastroenterologist", "ml-latin"),  # a bit of gas
    ("kaal cheruthayi kadayunnu, nadannathinu shesham", "self_care", "orthopaedician", "ml-latin"),  # leg slightly sore after walking
    ("neriya chuma, pani illa", "self_care", "general_physician", "ml-latin"),  # slight cough, no fever
]
