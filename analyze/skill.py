import os
import re
import json
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


from openai import OpenAI

client = OpenAI()

functions = [
    {
        "name": "extract_job_requirements",
        "description": "Extract required skills and years of experience from a job description.",
        "parameters": {
            "type": "object",
            "properties": {
                "required_skills": {"type": "array", "items": {"type": "string"}},
                "years_experience": {
                    "type": "integer",
                    "description": (
                        "Number of years required. "
                        "0 if not mentioned at all, "
                        "1 if 'experience' is mentioned but no number given."
                    ),
                },
            },
            "required": ["required_skills", "years_experience"],
        },
    }
]


def extract_requirements(job_text: str):
    """ChatGTP writes a function for ChatGPT"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a JSON extractor.  Given a LinkedIn job description, "
                    "return ONLY JSON with keys: required_skills (string array), "
                    "years_experience (integer).  "
                    "If it mentions X years of experience use X; "
                    "if it says 'experience' but gives no number, return 1; "
                    "if no experience requirement at all, return 0."
                ),
            },
            {"role": "user", "content": job_text},
        ],
        functions=functions,
        function_call={"name": "extract_job_requirements"},
    )

    # Pull out the function_call and parse its JSON arguments
    fn_call = resp.choices[0].message.function_call
    args = json.loads(fn_call.arguments)

    # Post‐processing: if GPT gave 0 but there's an 'experience' mention, bump to 1
    if args.get("years_experience", 0) == 0:
        # looks for words like "experience", "experienced", etc.
        if re.search(r"\bexperience\b", job_text, re.IGNORECASE):
            args["years_experience"] = 1

    return args


if __name__ == "__main__":
    job_desc = """
    About the job
    As a member of the Development Team,
     you will contribute to the code of world-class games like Cooking Fever,
      Pocket Styler, Airplane Chefs, and new games currently in development.
       Your work will make an impact on the experience of millions of players around the world.
        You will learn new things, test original ideas, collaborate with many different professionals,
         and embrace your own growth and development. Your friends will be proud of you, knowing,
          that you were the hero behind those games!
    
    
    Your Key Responsibilities:
    
    Developing and improving high-quality code in games that thousands of people play daily;
    Optimizing and refactoring the code;
    Collaborating with other team members (other programmers, game designers, artists, QA);
    Teaching others and sharing your expertise and knowledge;
    Designing game and game development tool architecture and supervising implementation.
    
    
    A Successful Candidate Must Have:
    
    Experience in commercial software or game development;
    Strong proficiency in C/C++ and Typescript;
    Experience in game development with Unity engine and C#;
    Great knowledge of Visual Studio and its debugging tools;
    Experience with Android and/or iOS;
    Grasp of KISS, DRY, YAGNI principles;
    Exceptional skills in math and geometry;
    Knowledge of 3D programming;
    Proficiency in optimizations;
    Knowledge of the principles of work via Jira, Git, etc.;
    Familiarity with databases (MongoDB, Redis);
    Experience with shading and rendering pipelines;
    Proficiency in networking;
    Understanding of physics and ability to implement physics in code;
    Curiosity – the desire to understand how the games are built and improve them;
    Good English language skills.
    
    
    Extra Great to Have:
    
    Passion for video games;
    Knowledge of at least one of the programming languages – Java, JavaScript, Objective-C;
    Knowledge of ECS/DOTS.
    
    
    Why "Nord Company"?
    
    We create world-class games that are loved by millions;
    We love to learn new things and strive for continuous self-development;
    We are eager to share our knowledge through Level Up Talks and take advantage of our book libraries;
    We are committed to maintaining our environment stress-free to support creativity and quality work;
    We take care of our health by maintaining work-life balance and enjoying various discounts on sports activities, medical check-ups, and other wellness perks;
    We take advantage of additional health insurance or wellness platform (after a year with us);
    We are proud to be a part of the socially responsible company as a part of our company's income is donated to those in need;
    We treat ourselves to free drinks and fresh fruits every day, weekly Friday breakfasts, monthly Friday evening get-togethers, and many more fun activities together;
    We take time to relax by playing, whether it's football, pool or table tennis, and - for sure - we enjoy video games on all sorts of consoles and platforms;
    We meet daily, weekly, and monthly to socialize, have fun, and celebrate being together.
    
    
    Salary: From 4200 EUR/month (gross), based on experience and competence
    """
    result = extract_requirements(job_desc)
    print(result)
    # → {'required_skills': [...], 'years_experience': 5}
