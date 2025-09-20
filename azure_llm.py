import os
from crewai.llm import LLM

def get_azure_llm():
    """Configure CrewAI LLM for Azure OpenAI."""
    azure_model = os.getenv("AZURE_MODEL_NAME")
    azure_deployment = os.getenv("AZURE_DEPLOYMENT_NAME")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_ENDPOINT")
    api_version = os.getenv("OPENAI_API_VERSION")

    return LLM(
        model=f"azure/{azure_model}",  # LiteLLM expects azure/<model-name>
        api_key=api_key,
        api_base=endpoint,
        api_version=api_version,
        deployment_name=azure_deployment,
    )
