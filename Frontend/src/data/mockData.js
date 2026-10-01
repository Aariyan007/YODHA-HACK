// Mock API responses. Generated from the real backend, so shapes match exactly.
// Used when VITE_USE_MOCK=true. Keep in sync with BackEnd/app/schemas.py.

export const login = {
  "token": "mock-token",
  "profile": {
    "id": "ammini01",
    "name": "Ammini Varghese",
    "phone": "9876543210",
    "age": 62,
    "gender": "Female",
    "bloodGroup": "B+",
    "abhaId": "91-4521-7788-3300",
    "language": "ml",
    "conditions": [
      "Type 2 Diabetes",
      "Hypertension",
      "High cholesterol"
    ],
    "allergies": [
      "Sulfa drugs"
    ]
  }
};

export const timeline = [
  {
    "id": "doc8",
    "date": "2026-09-24",
    "type": "prescription",
    "title": "Throat infection medicines",
    "source": "Dr. Anil Menon, PHC Ettumanoor",
    "summary": "Clarithromycin 500 twice a day for 7 days for throat infection. Metformin 500 was also written.",
    "summaryMl": "തൊണ്ടയിലെ അണുബാധയ്ക്ക് 7 ദിവസം Clarithromycin 500 ദിവസം രണ്ടു നേരം. Metformin 500-ഉം എഴുതിയിട്ടുണ്ട്.",
    "tags": [
      "infection"
    ],
    "items": [
      {
        "name": "Clarithromycin 500",
        "generic": "clarithromycin",
        "dose": "500 mg",
        "frequency": "Twice daily",
        "duration": "7 days"
      },
      {
        "name": "Metformin 500",
        "generic": "metformin",
        "dose": "500 mg",
        "frequency": "Twice daily",
        "duration": "Ongoing"
      }
    ]
  },
  {
    "id": "doc7",
    "date": "2026-03-05",
    "type": "lab",
    "title": "HbA1c and lipid profile",
    "source": "DDRC Agilus, Kottayam",
    "summary": "Sugar average is 7.2%, close to target. LDL dropped to 118, better but still above 100.",
    "summaryMl": "പഞ്ചസാര ശരാശരി 7.2%, ലക്ഷ്യത്തോട് അടുത്തു. LDL 118 ആയി കുറഞ്ഞു, പക്ഷേ ഇപ്പോഴും 100-ൽ കൂടുതൽ.",
    "tags": [
      "diabetes",
      "cholesterol"
    ],
    "items": [
      {
        "code": "hba1c",
        "name": "HbA1c",
        "value": 7.2,
        "unit": "%",
        "status": "watch",
        "range": "< 7.0 (diabetic target)"
      },
      {
        "code": "ldl",
        "name": "LDL cholesterol",
        "value": 118,
        "unit": "mg/dL",
        "status": "watch",
        "range": "< 100"
      },
      {
        "code": "hdl",
        "name": "HDL cholesterol",
        "value": 46,
        "unit": "mg/dL",
        "status": "good",
        "range": "> 40"
      },
      {
        "code": "fbs",
        "name": "Fasting blood sugar",
        "value": 128,
        "unit": "mg/dL",
        "status": "good",
        "range": "70 - 130"
      }
    ]
  },
  {
    "id": "doc6",
    "date": "2025-12-10",
    "type": "lab",
    "title": "HbA1c and kidney test",
    "source": "DDRC Agilus, Kottayam",
    "summary": "Sugar average is 7.4%, getting better. Kidney test (creatinine 1.1) is normal.",
    "summaryMl": "പഞ്ചസാര ശരാശരി 7.4%, മെച്ചപ്പെടുന്നു. വൃക്ക പരിശോധന (ക്രിയാറ്റിനിൻ 1.1) സാധാരണമാണ്.",
    "tags": [
      "diabetes",
      "kidney"
    ],
    "items": [
      {
        "code": "hba1c",
        "name": "HbA1c",
        "value": 7.4,
        "unit": "%",
        "status": "watch",
        "range": "< 7.0 (diabetic target)"
      },
      {
        "code": "creatinine",
        "name": "Creatinine",
        "value": 1.1,
        "unit": "mg/dL",
        "status": "good",
        "range": "0.5 - 1.2"
      }
    ]
  },
  {
    "id": "doc5",
    "date": "2025-09-18",
    "type": "consultation",
    "title": "Diabetes follow-up visit",
    "source": "Dr. Thomas Kurian, Caritas Hospital",
    "summary": "Routine check. BP 132/84. Feet checked, no wounds. Advised 30 minutes walking daily and less rice at dinner.",
    "summaryMl": "പതിവ് പരിശോധന. ബിപി 132/84. കാലുകൾ പരിശോധിച്ചു, മുറിവുകളില്ല. ദിവസവും 30 മിനിറ്റ് നടക്കാനും രാത്രി ചോറ് കുറയ്ക്കാനും പറഞ്ഞു.",
    "tags": [
      "diabetes",
      "bp"
    ],
    "items": [
      {
        "code": "sbp",
        "name": "Systolic BP",
        "value": 132,
        "unit": "mmHg",
        "status": "watch",
        "range": "90 - 130"
      },
      {
        "code": "dbp",
        "name": "Diastolic BP",
        "value": 84,
        "unit": "mmHg",
        "status": "good",
        "range": "60 - 85"
      }
    ]
  },
  {
    "id": "doc4",
    "date": "2025-03-15",
    "type": "prescription",
    "title": "Cholesterol medicine added",
    "source": "Dr. Thomas Kurian, Caritas Hospital",
    "summary": "Atorva 20 added once at night to bring cholesterol down. Continue Glycomet and Telma.",
    "summaryMl": "കൊളസ്ട്രോൾ കുറയ്ക്കാൻ രാത്രി Atorva 20 ചേർത്തു. Glycomet, Telma തുടരുക.",
    "tags": [
      "cholesterol"
    ],
    "items": [
      {
        "name": "Atorva 20",
        "generic": "atorvastatin",
        "dose": "20 mg",
        "frequency": "Once at night",
        "duration": "Ongoing"
      }
    ]
  },
  {
    "id": "doc3",
    "date": "2025-03-12",
    "type": "lab",
    "title": "HbA1c and lipid profile",
    "source": "DDRC Agilus, Kottayam",
    "summary": "Sugar average improved to 7.9%. LDL (bad cholesterol) is 142, which is above the target of 100.",
    "summaryMl": "പഞ്ചസാര ശരാശരി 7.9% ആയി മെച്ചപ്പെട്ടു. LDL (ചീത്ത കൊളസ്ട്രോൾ) 142 ആണ്, ലക്ഷ്യമായ 100-ൽ കൂടുതൽ.",
    "tags": [
      "diabetes",
      "cholesterol"
    ],
    "items": [
      {
        "code": "hba1c",
        "name": "HbA1c",
        "value": 7.9,
        "unit": "%",
        "status": "watch",
        "range": "< 7.0 (diabetic target)"
      },
      {
        "code": "ldl",
        "name": "LDL cholesterol",
        "value": 142,
        "unit": "mg/dL",
        "status": "watch",
        "range": "< 100"
      },
      {
        "code": "hdl",
        "name": "HDL cholesterol",
        "value": 44,
        "unit": "mg/dL",
        "status": "good",
        "range": "> 40"
      },
      {
        "code": "tg",
        "name": "Triglycerides",
        "value": 168,
        "unit": "mg/dL",
        "status": "watch",
        "range": "< 150"
      }
    ]
  },
  {
    "id": "doc2",
    "date": "2024-11-12",
    "type": "prescription",
    "title": "Diabetes and BP medicines",
    "source": "Dr. Thomas Kurian, Caritas Hospital",
    "summary": "Dr. Kurian started Glycomet 500 twice a day for sugar and Telma 40 once a day for blood pressure.",
    "summaryMl": "ഡോ. കുര്യൻ പഞ്ചസാരയ്ക്ക് Glycomet 500 ദിവസം രണ്ടു നേരവും, ബിപിക്ക് Telma 40 ദിവസം ഒരു നേരവും തുടങ്ങി.",
    "tags": [
      "diabetes",
      "bp"
    ],
    "items": [
      {
        "name": "Glycomet 500",
        "generic": "metformin",
        "dose": "500 mg",
        "frequency": "Twice daily",
        "duration": "Ongoing"
      },
      {
        "name": "Telma 40",
        "generic": "telmisartan",
        "dose": "40 mg",
        "frequency": "Once daily",
        "duration": "Ongoing"
      }
    ]
  },
  {
    "id": "doc1",
    "date": "2024-11-08",
    "type": "lab",
    "title": "HbA1c test",
    "source": "DDRC Agilus, Kottayam",
    "summary": "Your 3-month sugar average (HbA1c) is 9.1%. This is high. Your doctor will likely adjust your diabetes medicine.",
    "summaryMl": "നിങ്ങളുടെ മൂന്ന് മാസത്തെ ശരാശരി പഞ്ചസാര (HbA1c) 9.1% ആണ്. ഇത് കൂടുതലാണ്. ഡോക്ടർ മരുന്ന് മാറ്റിയേക്കാം.",
    "tags": [
      "diabetes"
    ],
    "items": [
      {
        "code": "hba1c",
        "name": "HbA1c",
        "value": 9.1,
        "unit": "%",
        "status": "alert",
        "range": "< 7.0 (diabetic target)"
      },
      {
        "code": "fbs",
        "name": "Fasting blood sugar",
        "value": 182,
        "unit": "mg/dL",
        "status": "alert",
        "range": "70 - 130"
      }
    ]
  }
];

export const alerts = [
  {
    "id": "alert1",
    "severity": "high",
    "kind": "interaction",
    "title": "Clarithromycin + Atorvastatin",
    "message": "Clarithromycin (new, from Dr. Menon) can raise Atorva levels and cause muscle damage. Show this to your doctor before taking both. Do not stop any medicine on your own.",
    "messageMl": "Clarithromycin (ഡോ. മേനോൻ എഴുതിയത്) Atorva-യുടെ അളവ് കൂട്ടി പേശികൾക്ക് ദോഷം ചെയ്യാം. രണ്ടും കഴിക്കുന്നതിന് മുമ്പ് ഡോക്ടറെ കാണിക്കുക. സ്വയം മരുന്ന് നിർത്തരുത്.",
    "resolved": false,
    "createdAt": "2026-09-24T10:30:00Z"
  },
  {
    "id": "alert2",
    "severity": "medium",
    "kind": "duplicate",
    "title": "Metformin written twice",
    "message": "Metformin 500 (Dr. Menon) is the same medicine as Glycomet 500 you already take. Taking both doubles the dose. Ask your doctor which one to take.",
    "messageMl": "Metformin 500 (ഡോ. മേനോൻ) നിങ്ങൾ ഇപ്പോൾ കഴിക്കുന്ന Glycomet 500-ന്റെ അതേ മരുന്നാണ്. രണ്ടും കഴിച്ചാൽ ഡോസ് ഇരട്ടിയാകും. ഏത് കഴിക്കണമെന്ന് ഡോക്ടറോട് ചോദിക്കുക.",
    "resolved": false,
    "createdAt": "2026-09-24T10:30:00Z"
  },
  {
    "id": "alert3",
    "severity": "low",
    "kind": "lab",
    "title": "LDL cholesterol above target",
    "message": "Your last LDL was 118 mg/dL. Target is below 100. Discuss at your next visit.",
    "messageMl": "അവസാന LDL 118 mg/dL ആയിരുന്നു. ലക്ഷ്യം 100-ൽ താഴെ. അടുത്ത സന്ദർശനത്തിൽ സംസാരിക്കുക.",
    "resolved": false,
    "createdAt": "2026-09-24T10:30:00Z"
  }
];

export const insights = {
  "summary": "Your sugar average (HbA1c) improved from 9.1% to 7.2%. Keep going.",
  "summaryMl": "നിങ്ങളുടെ പഞ്ചസാര ശരാശരി (HbA1c) 9.1%-ൽ നിന്ന് 7.2% ആയി മെച്ചപ്പെട്ടു. തുടരുക.",
  "conditions": [
    {
      "name": "Type 2 Diabetes",
      "since": "2016",
      "status": "watch"
    },
    {
      "name": "Hypertension",
      "since": "2018",
      "status": "good"
    },
    {
      "name": "High cholesterol",
      "since": "2025",
      "status": "watch"
    }
  ],
  "hba1c": [
    {
      "date": "2024-11-08",
      "value": 9.1
    },
    {
      "date": "2025-03-12",
      "value": 7.9
    },
    {
      "date": "2025-12-10",
      "value": 7.4
    },
    {
      "date": "2026-03-05",
      "value": 7.2
    }
  ],
  "labs": [
    {
      "code": "hba1c",
      "name": "HbA1c",
      "value": 7.2,
      "unit": "%",
      "date": "2026-03-05",
      "status": "watch",
      "range": "< 7.0 (diabetic target)"
    },
    {
      "code": "fbs",
      "name": "Fasting blood sugar",
      "value": 128.0,
      "unit": "mg/dL",
      "date": "2026-03-05",
      "status": "good",
      "range": "70 - 130"
    },
    {
      "code": "ldl",
      "name": "LDL cholesterol",
      "value": 118.0,
      "unit": "mg/dL",
      "date": "2026-03-05",
      "status": "watch",
      "range": "< 100"
    },
    {
      "code": "hdl",
      "name": "HDL cholesterol",
      "value": 46.0,
      "unit": "mg/dL",
      "date": "2026-03-05",
      "status": "good",
      "range": "> 40"
    },
    {
      "code": "tg",
      "name": "Triglycerides",
      "value": 168.0,
      "unit": "mg/dL",
      "date": "2025-03-12",
      "status": "watch",
      "range": "< 150"
    },
    {
      "code": "sbp",
      "name": "Systolic BP",
      "value": 132.0,
      "unit": "mmHg",
      "date": "2025-09-18",
      "status": "watch",
      "range": "90 - 130"
    },
    {
      "code": "dbp",
      "name": "Diastolic BP",
      "value": 84.0,
      "unit": "mmHg",
      "date": "2025-09-18",
      "status": "good",
      "range": "60 - 85"
    },
    {
      "code": "creatinine",
      "name": "Creatinine",
      "value": 1.1,
      "unit": "mg/dL",
      "date": "2025-12-10",
      "status": "good",
      "range": "0.5 - 1.2"
    }
  ]
};

export const medicines = [
  {
    "id": "med1",
    "name": "Glycomet 500",
    "generic": "metformin",
    "dose": "500 mg",
    "frequency": "Twice daily",
    "times": [
      "08:00",
      "20:00"
    ],
    "instructions": "After food",
    "startDate": "2024-11-12",
    "prescribedBy": "Dr. Thomas Kurian",
    "active": true
  },
  {
    "id": "med2",
    "name": "Telma 40",
    "generic": "telmisartan",
    "dose": "40 mg",
    "frequency": "Once daily",
    "times": [
      "08:00"
    ],
    "instructions": "Morning, before or after food",
    "startDate": "2024-11-12",
    "prescribedBy": "Dr. Thomas Kurian",
    "active": true
  },
  {
    "id": "med3",
    "name": "Atorva 20",
    "generic": "atorvastatin",
    "dose": "20 mg",
    "frequency": "Once at night",
    "times": [
      "21:00"
    ],
    "instructions": "At bedtime",
    "startDate": "2025-03-15",
    "prescribedBy": "Dr. Thomas Kurian",
    "active": true
  }
];

export const reminders = [
  {
    "key": "med1_0800",
    "medicineId": "med1",
    "name": "Glycomet 500",
    "dose": "500 mg",
    "instructions": "After food",
    "time": "08:00",
    "date": "2026-10-01",
    "taken": false
  },
  {
    "key": "med2_0800",
    "medicineId": "med2",
    "name": "Telma 40",
    "dose": "40 mg",
    "instructions": "Morning, before or after food",
    "time": "08:00",
    "date": "2026-10-01",
    "taken": false
  },
  {
    "key": "med1_2000",
    "medicineId": "med1",
    "name": "Glycomet 500",
    "dose": "500 mg",
    "instructions": "After food",
    "time": "20:00",
    "date": "2026-10-01",
    "taken": false
  },
  {
    "key": "med3_2100",
    "medicineId": "med3",
    "name": "Atorva 20",
    "dose": "20 mg",
    "instructions": "At bedtime",
    "time": "21:00",
    "date": "2026-10-01",
    "taken": false
  }
];

export const accessLog = [
  {
    "id": "ed9097205d7d",
    "who": "Dr. Anil Menon",
    "role": "Doctor",
    "action": "Viewed timeline",
    "via": "Share link",
    "at": "2026-09-24T13:15:03.183489Z"
  },
  {
    "id": "a51c55e0974e",
    "who": "Joseph Varghese",
    "role": "Family (Son)",
    "action": "Viewed medicines",
    "via": "Family access",
    "at": "2026-09-19T13:15:03.183489Z"
  },
  {
    "id": "5293cafa9810",
    "who": "Dr. Thomas Kurian",
    "role": "Doctor",
    "action": "Viewed full history",
    "via": "QR scan",
    "at": "2026-03-25T13:15:03.183489Z"
  }
];

export const family = [
  {
    "id": "fam1",
    "name": "Joseph Varghese",
    "relation": "Son",
    "phone": "9847001122",
    "canView": true,
    "notify": true
  },
  {
    "id": "fam2",
    "name": "Mariamma Thomas",
    "relation": "Daughter",
    "phone": "9847003344",
    "canView": true,
    "notify": false
  }
];

export const share = {
  "token": "demo-share",
  "url": "/share/demo-share",
  "scope": "full",
  "expiresAt": "2026-10-02T13:17:51.502781Z"
};

export const snapshot = {
  "patient": {
    "id": "ammini01",
    "name": "Ammini Varghese",
    "phone": "9876543210",
    "age": 62,
    "gender": "Female",
    "bloodGroup": "B+",
    "abhaId": "91-4521-7788-3300",
    "language": "ml",
    "conditions": [
      "Type 2 Diabetes",
      "Hypertension",
      "High cholesterol"
    ],
    "allergies": [
      "Sulfa drugs"
    ]
  },
  "scope": "full",
  "expiresAt": "2026-10-02T13:17:51.502781Z",
  "timeline": [
    {
      "id": "doc8",
      "date": "2026-09-24",
      "type": "prescription",
      "title": "Throat infection medicines",
      "source": "Dr. Anil Menon, PHC Ettumanoor",
      "summary": "Clarithromycin 500 twice a day for 7 days for throat infection. Metformin 500 was also written.",
      "summaryMl": "തൊണ്ടയിലെ അണുബാധയ്ക്ക് 7 ദിവസം Clarithromycin 500 ദിവസം രണ്ടു നേരം. Metformin 500-ഉം എഴുതിയിട്ടുണ്ട്.",
      "tags": [
        "infection"
      ],
      "items": [
        {
          "name": "Clarithromycin 500",
          "generic": "clarithromycin",
          "dose": "500 mg",
          "frequency": "Twice daily",
          "duration": "7 days"
        },
        {
          "name": "Metformin 500",
          "generic": "metformin",
          "dose": "500 mg",
          "frequency": "Twice daily",
          "duration": "Ongoing"
        }
      ]
    },
    {
      "id": "doc7",
      "date": "2026-03-05",
      "type": "lab",
      "title": "HbA1c and lipid profile",
      "source": "DDRC Agilus, Kottayam",
      "summary": "Sugar average is 7.2%, close to target. LDL dropped to 118, better but still above 100.",
      "summaryMl": "പഞ്ചസാര ശരാശരി 7.2%, ലക്ഷ്യത്തോട് അടുത്തു. LDL 118 ആയി കുറഞ്ഞു, പക്ഷേ ഇപ്പോഴും 100-ൽ കൂടുതൽ.",
      "tags": [
        "diabetes",
        "cholesterol"
      ],
      "items": [
        {
          "code": "hba1c",
          "name": "HbA1c",
          "value": 7.2,
          "unit": "%",
          "status": "watch",
          "range": "< 7.0 (diabetic target)"
        },
        {
          "code": "ldl",
          "name": "LDL cholesterol",
          "value": 118,
          "unit": "mg/dL",
          "status": "watch",
          "range": "< 100"
        },
        {
          "code": "hdl",
          "name": "HDL cholesterol",
          "value": 46,
          "unit": "mg/dL",
          "status": "good",
          "range": "> 40"
        },
        {
          "code": "fbs",
          "name": "Fasting blood sugar",
          "value": 128,
          "unit": "mg/dL",
          "status": "good",
          "range": "70 - 130"
        }
      ]
    },
    {
      "id": "doc6",
      "date": "2025-12-10",
      "type": "lab",
      "title": "HbA1c and kidney test",
      "source": "DDRC Agilus, Kottayam",
      "summary": "Sugar average is 7.4%, getting better. Kidney test (creatinine 1.1) is normal.",
      "summaryMl": "പഞ്ചസാര ശരാശരി 7.4%, മെച്ചപ്പെടുന്നു. വൃക്ക പരിശോധന (ക്രിയാറ്റിനിൻ 1.1) സാധാരണമാണ്.",
      "tags": [
        "diabetes",
        "kidney"
      ],
      "items": [
        {
          "code": "hba1c",
          "name": "HbA1c",
          "value": 7.4,
          "unit": "%",
          "status": "watch",
          "range": "< 7.0 (diabetic target)"
        },
        {
          "code": "creatinine",
          "name": "Creatinine",
          "value": 1.1,
          "unit": "mg/dL",
          "status": "good",
          "range": "0.5 - 1.2"
        }
      ]
    },
    {
      "id": "doc5",
      "date": "2025-09-18",
      "type": "consultation",
      "title": "Diabetes follow-up visit",
      "source": "Dr. Thomas Kurian, Caritas Hospital",
      "summary": "Routine check. BP 132/84. Feet checked, no wounds. Advised 30 minutes walking daily and less rice at dinner.",
      "summaryMl": "പതിവ് പരിശോധന. ബിപി 132/84. കാലുകൾ പരിശോധിച്ചു, മുറിവുകളില്ല. ദിവസവും 30 മിനിറ്റ് നടക്കാനും രാത്രി ചോറ് കുറയ്ക്കാനും പറഞ്ഞു.",
      "tags": [
        "diabetes",
        "bp"
      ],
      "items": [
        {
          "code": "sbp",
          "name": "Systolic BP",
          "value": 132,
          "unit": "mmHg",
          "status": "watch",
          "range": "90 - 130"
        },
        {
          "code": "dbp",
          "name": "Diastolic BP",
          "value": 84,
          "unit": "mmHg",
          "status": "good",
          "range": "60 - 85"
        }
      ]
    },
    {
      "id": "doc4",
      "date": "2025-03-15",
      "type": "prescription",
      "title": "Cholesterol medicine added",
      "source": "Dr. Thomas Kurian, Caritas Hospital",
      "summary": "Atorva 20 added once at night to bring cholesterol down. Continue Glycomet and Telma.",
      "summaryMl": "കൊളസ്ട്രോൾ കുറയ്ക്കാൻ രാത്രി Atorva 20 ചേർത്തു. Glycomet, Telma തുടരുക.",
      "tags": [
        "cholesterol"
      ],
      "items": [
        {
          "name": "Atorva 20",
          "generic": "atorvastatin",
          "dose": "20 mg",
          "frequency": "Once at night",
          "duration": "Ongoing"
        }
      ]
    },
    {
      "id": "doc3",
      "date": "2025-03-12",
      "type": "lab",
      "title": "HbA1c and lipid profile",
      "source": "DDRC Agilus, Kottayam",
      "summary": "Sugar average improved to 7.9%. LDL (bad cholesterol) is 142, which is above the target of 100.",
      "summaryMl": "പഞ്ചസാര ശരാശരി 7.9% ആയി മെച്ചപ്പെട്ടു. LDL (ചീത്ത കൊളസ്ട്രോൾ) 142 ആണ്, ലക്ഷ്യമായ 100-ൽ കൂടുതൽ.",
      "tags": [
        "diabetes",
        "cholesterol"
      ],
      "items": [
        {
          "code": "hba1c",
          "name": "HbA1c",
          "value": 7.9,
          "unit": "%",
          "status": "watch",
          "range": "< 7.0 (diabetic target)"
        },
        {
          "code": "ldl",
          "name": "LDL cholesterol",
          "value": 142,
          "unit": "mg/dL",
          "status": "watch",
          "range": "< 100"
        },
        {
          "code": "hdl",
          "name": "HDL cholesterol",
          "value": 44,
          "unit": "mg/dL",
          "status": "good",
          "range": "> 40"
        },
        {
          "code": "tg",
          "name": "Triglycerides",
          "value": 168,
          "unit": "mg/dL",
          "status": "watch",
          "range": "< 150"
        }
      ]
    },
    {
      "id": "doc2",
      "date": "2024-11-12",
      "type": "prescription",
      "title": "Diabetes and BP medicines",
      "source": "Dr. Thomas Kurian, Caritas Hospital",
      "summary": "Dr. Kurian started Glycomet 500 twice a day for sugar and Telma 40 once a day for blood pressure.",
      "summaryMl": "ഡോ. കുര്യൻ പഞ്ചസാരയ്ക്ക് Glycomet 500 ദിവസം രണ്ടു നേരവും, ബിപിക്ക് Telma 40 ദിവസം ഒരു നേരവും തുടങ്ങി.",
      "tags": [
        "diabetes",
        "bp"
      ],
      "items": [
        {
          "name": "Glycomet 500",
          "generic": "metformin",
          "dose": "500 mg",
          "frequency": "Twice daily",
          "duration": "Ongoing"
        },
        {
          "name": "Telma 40",
          "generic": "telmisartan",
          "dose": "40 mg",
          "frequency": "Once daily",
          "duration": "Ongoing"
        }
      ]
    },
    {
      "id": "doc1",
      "date": "2024-11-08",
      "type": "lab",
      "title": "HbA1c test",
      "source": "DDRC Agilus, Kottayam",
      "summary": "Your 3-month sugar average (HbA1c) is 9.1%. This is high. Your doctor will likely adjust your diabetes medicine.",
      "summaryMl": "നിങ്ങളുടെ മൂന്ന് മാസത്തെ ശരാശരി പഞ്ചസാര (HbA1c) 9.1% ആണ്. ഇത് കൂടുതലാണ്. ഡോക്ടർ മരുന്ന് മാറ്റിയേക്കാം.",
      "tags": [
        "diabetes"
      ],
      "items": [
        {
          "code": "hba1c",
          "name": "HbA1c",
          "value": 9.1,
          "unit": "%",
          "status": "alert",
          "range": "< 7.0 (diabetic target)"
        },
        {
          "code": "fbs",
          "name": "Fasting blood sugar",
          "value": 182,
          "unit": "mg/dL",
          "status": "alert",
          "range": "70 - 130"
        }
      ]
    }
  ],
  "medicines": [
    {
      "id": "med1",
      "name": "Glycomet 500",
      "generic": "metformin",
      "dose": "500 mg",
      "frequency": "Twice daily",
      "times": [
        "08:00",
        "20:00"
      ],
      "instructions": "After food",
      "startDate": "2024-11-12",
      "prescribedBy": "Dr. Thomas Kurian",
      "active": true
    },
    {
      "id": "med2",
      "name": "Telma 40",
      "generic": "telmisartan",
      "dose": "40 mg",
      "frequency": "Once daily",
      "times": [
        "08:00"
      ],
      "instructions": "Morning, before or after food",
      "startDate": "2024-11-12",
      "prescribedBy": "Dr. Thomas Kurian",
      "active": true
    },
    {
      "id": "med3",
      "name": "Atorva 20",
      "generic": "atorvastatin",
      "dose": "20 mg",
      "frequency": "Once at night",
      "times": [
        "21:00"
      ],
      "instructions": "At bedtime",
      "startDate": "2025-03-15",
      "prescribedBy": "Dr. Thomas Kurian",
      "active": true
    }
  ],
  "alerts": [
    {
      "id": "alert1",
      "severity": "high",
      "kind": "interaction",
      "title": "Clarithromycin + Atorvastatin",
      "message": "Clarithromycin (new, from Dr. Menon) can raise Atorva levels and cause muscle damage. Show this to your doctor before taking both. Do not stop any medicine on your own.",
      "messageMl": "Clarithromycin (ഡോ. മേനോൻ എഴുതിയത്) Atorva-യുടെ അളവ് കൂട്ടി പേശികൾക്ക് ദോഷം ചെയ്യാം. രണ്ടും കഴിക്കുന്നതിന് മുമ്പ് ഡോക്ടറെ കാണിക്കുക. സ്വയം മരുന്ന് നിർത്തരുത്.",
      "resolved": false,
      "createdAt": "2026-09-24T10:30:00Z"
    },
    {
      "id": "alert2",
      "severity": "medium",
      "kind": "duplicate",
      "title": "Metformin written twice",
      "message": "Metformin 500 (Dr. Menon) is the same medicine as Glycomet 500 you already take. Taking both doubles the dose. Ask your doctor which one to take.",
      "messageMl": "Metformin 500 (ഡോ. മേനോൻ) നിങ്ങൾ ഇപ്പോൾ കഴിക്കുന്ന Glycomet 500-ന്റെ അതേ മരുന്നാണ്. രണ്ടും കഴിച്ചാൽ ഡോസ് ഇരട്ടിയാകും. ഏത് കഴിക്കണമെന്ന് ഡോക്ടറോട് ചോദിക്കുക.",
      "resolved": false,
      "createdAt": "2026-09-24T10:30:00Z"
    },
    {
      "id": "alert3",
      "severity": "low",
      "kind": "lab",
      "title": "LDL cholesterol above target",
      "message": "Your last LDL was 118 mg/dL. Target is below 100. Discuss at your next visit.",
      "messageMl": "അവസാന LDL 118 mg/dL ആയിരുന്നു. ലക്ഷ്യം 100-ൽ താഴെ. അടുത്ത സന്ദർശനത്തിൽ സംസാരിക്കുക.",
      "resolved": false,
      "createdAt": "2026-09-24T10:30:00Z"
    }
  ],
  "insights": {
    "summary": "Your sugar average (HbA1c) improved from 9.1% to 7.2%. Keep going.",
    "summaryMl": "നിങ്ങളുടെ പഞ്ചസാര ശരാശരി (HbA1c) 9.1%-ൽ നിന്ന് 7.2% ആയി മെച്ചപ്പെട്ടു. തുടരുക.",
    "conditions": [
      {
        "name": "Type 2 Diabetes",
        "since": "2016",
        "status": "watch"
      },
      {
        "name": "Hypertension",
        "since": "2018",
        "status": "good"
      },
      {
        "name": "High cholesterol",
        "since": "2025",
        "status": "watch"
      }
    ],
    "hba1c": [
      {
        "date": "2024-11-08",
        "value": 9.1
      },
      {
        "date": "2025-03-12",
        "value": 7.9
      },
      {
        "date": "2025-12-10",
        "value": 7.4
      },
      {
        "date": "2026-03-05",
        "value": 7.2
      }
    ],
    "labs": [
      {
        "code": "hba1c",
        "name": "HbA1c",
        "value": 7.2,
        "unit": "%",
        "date": "2026-03-05",
        "status": "watch",
        "range": "< 7.0 (diabetic target)"
      },
      {
        "code": "fbs",
        "name": "Fasting blood sugar",
        "value": 128.0,
        "unit": "mg/dL",
        "date": "2026-03-05",
        "status": "good",
        "range": "70 - 130"
      },
      {
        "code": "ldl",
        "name": "LDL cholesterol",
        "value": 118.0,
        "unit": "mg/dL",
        "date": "2026-03-05",
        "status": "watch",
        "range": "< 100"
      },
      {
        "code": "hdl",
        "name": "HDL cholesterol",
        "value": 46.0,
        "unit": "mg/dL",
        "date": "2026-03-05",
        "status": "good",
        "range": "> 40"
      },
      {
        "code": "tg",
        "name": "Triglycerides",
        "value": 168.0,
        "unit": "mg/dL",
        "date": "2025-03-12",
        "status": "watch",
        "range": "< 150"
      },
      {
        "code": "sbp",
        "name": "Systolic BP",
        "value": 132.0,
        "unit": "mmHg",
        "date": "2025-09-18",
        "status": "watch",
        "range": "90 - 130"
      },
      {
        "code": "dbp",
        "name": "Diastolic BP",
        "value": 84.0,
        "unit": "mmHg",
        "date": "2025-09-18",
        "status": "good",
        "range": "60 - 85"
      },
      {
        "code": "creatinine",
        "name": "Creatinine",
        "value": 1.1,
        "unit": "mg/dL",
        "date": "2025-12-10",
        "status": "good",
        "range": "0.5 - 1.2"
      }
    ]
  }
};

// ---------- Phase 2: upload pipeline + triage mocks ----------

export const demoUpload = {
  record: {
    id: "doc_demo_upload",
    date: "2026-09-28",
    type: "prescription",
    status: "good",
    title: "Cough and fever",
    provider: "Sunrise Clinic, Kottayam",
    doctor: "Dr Rahul Das",
    summary: {
      en: "You visited Dr Rahul Das at Sunrise Clinic for cough and fever. Take Clarithromycin 500 mg twice a day after food for 7 days, continue Glycomet 500 mg twice a day, Ascoril syrup 10 ml three times a day for 5 days, and Dolo 650 mg only when fever rises. Come back after 5 days if the fever is still there.",
      ml: "ഡോ. രാഹുൽ ദാസ്, സൺറൈസ് ക്ലിനിക്, കോട്ടയം എന്നിവിടങ്ങളിൽ ചുമയും ജ്വരവും പരിശോധിച്ചു. Clarithromycin 500 mg ദിവസം രണ്ടുതവണ ഭക്ഷണത്തിന് ശേഷം 7 ദിവസം, Glycomet 500 mg ദിവസം രണ്ടുതവണ തുടരുക, Ascoril സിറപ്പ് 10 ml ദിവസം മൂന്നുതവണ 5 ദിവസം, ജ്വരം വന്നാൽ മാത്രം Dolo 650 mg എടുക്കുക. 5 ദിവസം കഴിഞ്ഞും ജ്വരം തുടർന്നാൽ വീണ്ടും വരിക."
    },
    observations: [],
    medications: [
      { name: "Tab Clarithromycin 500 mg", generic: "clarithromycin", dose: "500 mg", schedule: "BD", times: ["08:00", "20:00"], duration: "7 days", purpose: "cough and fever" },
      { name: "Tab Glycomet 500 mg", generic: "metformin", dose: "500 mg", schedule: "BD", times: ["08:00", "20:00"], duration: "continue", purpose: "diabetes" },
      { name: "Syp Ascoril 10 ml", generic: "cough-syrup", dose: "10 ml", schedule: "TDS", times: ["08:00", "14:00", "20:00"], duration: "5 days", purpose: "cough" },
      { name: "Tab Dolo 650 mg", generic: "paracetamol", dose: "650 mg", schedule: "SOS", times: [], duration: null, purpose: "fever" }
    ],
    followUp: "Review after 5 days if fever persists.",
    source: {
      kind: "image",
      lines: [
        "Sunrise Clinic, Kottayam",
        "Dr Rahul Das, MBBS",
        "Date: 28/09/2026",
        "C/O: Cough and fever x 4 days",
        "Tab Clarithromycin 500 mg - BD x 7 days",
        "Tab Glycomet 500 mg - BD (continue)",
        "Syp Ascoril 10 ml - TDS x 5 days",
        "Review after 5 days if fever persists."
      ],
      highlight: [0, 1, 4, 5, 6, 7]
    },
    isNew: true
  },
  alerts: [
    {
      id: "alert_demo_dup",
      severity: "high",
      kind: "duplicate",
      title: "Tab Glycomet duplicates Glycomet 500",
      message: "Tab Glycomet is the same medicine as Glycomet 500 you are already taking (both are metformin). Taking both doubles the dose. Ask your doctor which one to continue.",
      messageMl: null,
      resolved: false,
      createdAt: "2026-09-28T10:00:00Z"
    },
    {
      id: "alert_demo_clash",
      severity: "high",
      kind: "clash",
      title: "Tab Clarithromycin + Atorva 20",
      message: "Clarithromycin raises atorvastatin levels in blood, which can cause serious muscle damage. Doctor should pause atorvastatin while on clarithromycin.",
      messageMl: null,
      resolved: false,
      createdAt: "2026-09-28T10:00:00Z"
    }
  ],
  reminders: [
    { id: "rem1", title: "Tab Clarithromycin 500 mg", when: "2026-09-29T08:00:00+05:30", until: "2026-10-05", time: "08:00" },
    { id: "rem2", title: "Tab Glycomet 500 mg",       when: "2026-09-29T08:00:00+05:30", until: null,          time: "08:00" },
    { id: "rem3", title: "Syp Ascoril 10 ml",         when: "2026-09-29T08:00:00+05:30", until: "2026-10-03", time: "08:00" },
    { id: "rem4", title: "Syp Ascoril 10 ml",         when: "2026-09-29T14:00:00+05:30", until: "2026-10-03", time: "14:00" },
    { id: "rem5", title: "Tab Clarithromycin 500 mg", when: "2026-09-29T20:00:00+05:30", until: "2026-10-05", time: "20:00" },
    { id: "rem6", title: "Tab Glycomet 500 mg",       when: "2026-09-29T20:00:00+05:30", until: null,          time: "20:00" },
    { id: "rem7", title: "Syp Ascoril 10 ml",         when: "2026-09-29T20:00:00+05:30", until: "2026-10-03", time: "20:00" },
    { id: "rem8", title: "Follow-up: Review after 5 days if fever persists.", when: "2026-10-05T10:00:00+05:30", until: "2026-10-05", time: "10:00" }
  ]
};

// Keyword-based triage, mirrors BackEnd/app/routers/documents.py SYMPTOM_RULES.
export const symptomRules = [
  { patterns: /chest\s+pain|heart\s+attack/i,   specialist: "Emergency / 108",            why: "Possible chest pain. Call 108 immediately or go to the nearest emergency room.", urgent: true },
  { patterns: /can'?t\s+breathe|short(ness)?\s+of\s+breath|breathless/i, specialist: "Emergency / 108", why: "Possible trouble breathing. Call 108 immediately.", urgent: true },
  { patterns: /face\s+droop|slurred\s+speech|weak(ness)?\s+(on\s+)?one\s+side|stroke/i, specialist: "Emergency / 108", why: "Possible signs of stroke. Call 108 immediately.", urgent: true },
  { patterns: /faint|unconscious|passed\s+out/i, specialist: "Emergency / 108",           why: "Possible fainting. Seek urgent care.", urgent: true },
  { patterns: /chest|breath|palpit|heart/i,     specialist: "Cardiologist",                why: "Heart-related symptoms" },
  { patterns: /sugar|diabetes|thirst|hba1c/i,   specialist: "Diabetologist / Endocrinologist", why: "Possible diabetes-related issue" },
  { patterns: /blood pressure|bp|dizzy|headache/i, specialist: "General Physician",       why: "Blood-pressure or general assessment" },
  { patterns: /tooth|gum|dental/i,              specialist: "Dentist",                     why: "Dental issue" },
  { patterns: /eye|vision|blurry|cataract/i,    specialist: "Ophthalmologist",             why: "Eye-related issue" },
  { patterns: /ear|hearing|vertigo/i,           specialist: "ENT specialist",              why: "Ear or balance issue" },
  { patterns: /skin|rash|itch|eczema/i,         specialist: "Dermatologist",               why: "Skin issue" },
  { patterns: /joint|knee|back pain|arthritis/i,specialist: "Orthopaedician",              why: "Joint or muscle issue" },
  { patterns: /period|pregnan|menstrual|pcos/i, specialist: "Gynaecologist",               why: "Women's health" },
  { patterns: /child|baby|infant/i,             specialist: "Paediatrician",               why: "Child health" },
  { patterns: /anxiety|depress|sad|stress/i,    specialist: "Psychiatrist / Psychologist", why: "Mental health concern" },
  { patterns: /stomach|vomit|diarrhoea|acid/i,  specialist: "Gastroenterologist / Physician", why: "Digestive issue" },
  { patterns: /urine|kidney|urinary/i,          specialist: "Nephrologist / Urologist",    why: "Kidney or urinary issue" },
  { patterns: /fever|cold|cough|throat|flu/i,   specialist: "General Physician",           why: "Common infection" }
];

export function mockTriage(text) {
  const match = symptomRules.find((r) => r.patterns.test(text));
  if (match) return { urgent: Boolean(match.urgent), specialist: match.specialist, why: match.why };
  return { urgent: false, specialist: "General Physician", why: "A general check-up is a good starting point." };
}
