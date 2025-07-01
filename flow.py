from pocketflow import Flow
# Import all node classes from nodes.py
from nodes import (
    FetchRepo,
    IdentifyAbstractions,
    AnalyzeRelationships,
    OrderChapters,
    WriteChapters,
    CombineTutorial,
    WriteBeginnerFriendlyEpisode
)

def create_tutorial_flow():
    """Creates and returns the codebase tutorial generation flow."""

    # Instantiate nodes
    fetch_repo = FetchRepo()
    identify_abstractions = IdentifyAbstractions(max_retries=5, wait=20)
    analyze_relationships = AnalyzeRelationships(max_retries=5, wait=20)
    order_chapters = OrderChapters(max_retries=5, wait=20)
    write_chapters = WriteChapters(max_retries=5, wait=20) # This is a BatchNode
    write_beginner_friendly_episode = WriteBeginnerFriendlyEpisode(max_retries=3, wait=10)
    combine_tutorial = CombineTutorial()

    # Connect nodes in sequence based on the design
    fetch_repo >> identify_abstractions
    identify_abstractions >> analyze_relationships
    analyze_relationships >> order_chapters
    order_chapters >> write_chapters
    write_chapters >> write_beginner_friendly_episode
    write_beginner_friendly_episode >> combine_tutorial

    # Create the flow starting with FetchRepo
    tutorial_flow = Flow(start=fetch_repo)

    return tutorial_flow
