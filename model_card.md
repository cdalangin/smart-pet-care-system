# What are the limitations or biases in your system?

The functionality is limited and suggestions come from a fixed list for five species (dog, cat, fish, rabbit, hamster). Gemini only sees pet names, species and task names, so it has no idea about a pet's age, breed or health and can't make tailored suggestions for those different variables. It also assumes a daytime schedule (07:00 to 21:00) and plans greedily by priority, so a task can get dropped even if a smarter plan could've fit it.

# Could your AI be misused, and how would you prevent that?

The biggest risk is someone treating the suggestions like real vet advice, so I set up suggestions as always low priority and never replace the owner's own tasks. Maybe another guardrail is to put a note that says "this is not vet advice" in the app. Another way it could be misued is if someone typed weird instructions into a pet or task name to mess with the Gemini prompt. To handle this i treat the input as plain data in the prompt and checking everything Gemini returns in code, so a bad answer can't put an invalid task in the schedule.

# What surprised you while testing your AI's reliability?

I thought the hard part would be the scheduling logic, but the API caused most of the problems. I got multiple different errors trying to call the api like a "client has been closed" error, a retired model name error, 503 "high demand" errors, and a spinner that just hung forever. The tests with a fake Gemini client passed the whole time, so those bugs only showed up when I ran it for real. Also when I was adding functionality to my system, it would break some old functionality and break old tests, so I had to make sure to make the appropriate updates for those outdated parts to keep the whole project intact. 

# Describe your collaboration with AI during this project. 

While working through the project, I used the AI to figure out ways to outline the task suggestions in the schedule. Originally it suggested to add them to where you input the pet's tasks, but it ended up looking too crowded and didn't seem as user friendly. I changed it to be moved in the schedule builder instead, and that also helped make a clear distinction between user inputted tasks and suggestions. The AI's suggestion for implementing the suggestions was also limiting because it would pick a random time to put the task, but I updated it where the user gets to choose where to put it in the schedule. 