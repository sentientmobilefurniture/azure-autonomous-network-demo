1. Please fix the graph visualizer on the main page so that when you select or deselect nodes, the graph does not recenter.
2. Please add an additional bar below the nodes to control edge display in a similar style.
3. Please add a setting to each bar, node and edge, to control the size and color of display text.
4. For the visualizer in the view graph in conversation cards, freeze the graph by default.
5. We need to figure out how to keep fabric warm
6. Remove min and max limits on the resizing of each element. We should be able to resize each element without limit, down or up. That means potentially allowing an element to disappear by sizing it down, or cover the whole screen by sizing it up.
7. Please update resource tab - To show a graph of the entire agent. Cover every single deployment and infrastructure element, every agent, every container, every API app, every tool, etc... The purpose is to show the user the entire service architecure to support the narrative. Currently I think it is being generated from scenario. Let us create a file and display it instead. Similar to the way the main graph visualizer is done, except we don't create the graph from a file, we just create it manually. Add a tool tip to resources tab noting that this regeneration must be done if architecture changes or new tools are added. 
8. Most important requirement. All of this must not break or remove ANY existing functionality. It is addition, not deletion.
9. You must do your best to avoid contradictions and implementation breakages. be extremely careful and thorough. Audit against existing codebase state.
