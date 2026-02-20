1. Do data analysis over alerts directly Focus on TWO ALERT storm scenarios. SCREW THE OTHER DEMO FLOWS
2. Fiber cut scenario 
3. Wear and tear scenario 
4. Add simulated Action calls - Make sure there is a unique block that appears during the thread that simulates an action done by the orchestrator - let orchestrator fire actions during the flow
IDEAL ACTION: Fire email to the man stationed at the relay - NEW DATA SOURCE! DUTY ROSTER!!!!!!!! MAN, EMAIL, LOCATION, PHONE NUMBER!!!!!!!!!!!!! CONTACT HIM - TELL HIM TO GET IN HIS DAMN TRUCK AND RIDE TO THE PROBLEM SITE AND LOOK FOR THESE PHYSICAL SIGNS!
CAN WE GIVE HIM THE SENSOR LOCATION SO THAT HE KNOWS EXACRLT WHERE TO GO!
WE NEED TO UPDATE THE TELEMETRY TO INCLUDE INDIVIDUAL SENSORS - WHICH SENSOR GAVE WHAT READING?
WE NEED A NEW TABLE IN COSMOS DB TELLING GIVING US THE SENSOR DATA AND THE PHYSICAL LOCATION OF THAT SENSOR! AND WHAT IT MONITORS!!
WE NEED PHYSICAL COORDINATES FOR EACH STRUCTURE!
WE NEED A NEW TABLE IN COSMOS DB GIVING US A DUTY ROSTER WITH POINTS OF CONTACT, IT HAS TO BE SEARCHABLE BY DATE AND LOCATION PRIMARILY!!!!!!
WE NEED TO THEREFORE BE ABLE TO TO TELL THE DUTY GUY TO ACT!
updates to orchestrator prompt are needed! AND WE SHOULD FIGURE
Revamp to scenario data is needed!
Let us add to the orchestrator a tool (Reference: https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/function-calling?view=foundry&preserve-view=true&pivots=python, https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/openapi?view=foundry&pivots=python)
This tool will be used to fire an email to whoever is identified in the duty roster! (But actually, that email will always be defined by PRESENTER_EMAIL - User defined var in /home/hanchoong/backup/azure-autonomous-network-demo/fabricdemo/azure_config.env.template)
Can we find any relevant reference at all in /home/hanchoong/references/skills/.agents/skills? 
Do note down every reference you used including online URLS
THE ORCHESTRATOR AGENT WILL CALL THIS TOOL TO ALERT THE PERSON BY WRITING AN EMAIL! And the email should be viewable by clicking a (View action) button on the right side of the action card as it appears in the scrolling chat window! And if we can get the email to appear in the presenter's outlook that is a bonus but not required. I am not sure how we can send an email and have it be legit tho...... Maybe we should just have the tool spoof the effect. We show that it was called and then we just display the email for demo purpose? WELL Let's keep the presenter email var for a future where we actually implement the function.

