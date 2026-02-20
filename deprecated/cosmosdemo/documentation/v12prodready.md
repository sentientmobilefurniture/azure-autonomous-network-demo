1. Add follow up actions
2. Add real alerting infrastructure with alert generators
3. For telco-backbone, need prompts + alerting that allows us to show the full suite of multiagent execution - Maybe change the validator
4. Remove that "validating thing". Have there be a button to explicitly retriev available scenarios

Can we rethink the header for clean tabs side by side?

Scenario dropdown where each entry has an edit button that takes you to an edit page. And this edit page allows you to see the contents of the DBs in cosmos and explicitly select which graph, which telemetry, which prompts for which agent, obviously set to the scenario settings as default. And if you click save, it rewires everything. 

Oh. Also, the form for adding the new scenario should continue running even when you close it. I'm thinking there should be a scenario status tab next to the scenario dropdown menu, where you can see the current status of scenarios being uploaded. Like you see the scenario name, and then below it in a tree structure type deal, you see the individual components and their individual status, and the current overall status of the uploaded scenario is up above. These uploads should persist even when you aren't looking at them or when you close the browser, if that is at all possible. And when you look at it, you should be able to see the statuses of past uploads

Actually...Can we evolve to have a scenario edit screen instead? Make it its own tab? Basically allowing you to CRUD prompts in the UI

5. Full suite of acceptance tests