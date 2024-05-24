import pendulum 
import os
import json
import asyncio
import semantic_kernel as sk    # make sure you are using semantic-kernel 0.5.1.dev0 (pip install semantic-kernel==0.5.1.dev0)
from src.data.UWOtools import *
import logging
from opentelemetry import metrics
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

load_dotenv()




# Home: https://github.com/microsoft/semantic-kernel
# documentation: https://learn.microsoft.com/en-us/semantic-kernel/overview/
# deploy a model on Azure OpenAI: https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/create-resource?pivots=web-portal#confirm-the-configuration-and-create-the-resource


# global definitions
plugins_directory = "./src/data/plugins-sk"
useAzureOpenAI = True


def get_kernel() -> sk.Kernel:
    """Returns a (semantic) kernel with all plugins loaded."""
    # https://opentelemetry.io/docs/languages/python/getting-started/
    # TODO add logging and telemetry https://devblogs.microsoft.com/semantic-kernel/unlock-the-power-of-telemetry-in-semantic-kernel-sdk/

    # Acquire a meter.
    meter = metrics.get_meter("OpenAI.meter")
    request_counter = meter.create_counter(
        "request_processed",
        description="The number of requests that got processed",
    )
    # # Configure basic logger
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    kernel = sk.Kernel()

    if useAzureOpenAI:
        from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

        # to load the .env file, the current directory needs to be the root of the project
        deployment, api_key, endpoint = sk.azure_openai_settings_from_dot_env() # type: ignore

        # Logging that Azure OpenAI is being used
        logger.info("Configuring kernel with Azure OpenAI text completion service.")

        # get the kernel
        kernel.add_text_completion_service("azureopenai", AzureChatCompletion(deployment_name=deployment, endpoint=endpoint, api_key=api_key))
        request_counter.add(1, {"service": "AzureOpenAI", "action": "TextCompletion"})
    else:
        logger.info("Azure OpenAI not configured. Falling back to alternative configuration.")
        pass
        from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

        # this is for the wrong semantic-kernal version
        # api_key, org_id = sk.openai_settings_from_dot_env()
        # service_id = "openai_chat_gpt"
        # kernel.add_service(OpenAIChatCompletion(service_id=service_id, ai_model_id="gpt-3.5-turbo-1106", # try gpt-4-1106-preview
        #                                         api_key=api_key, org_id=org_id))
                                                                            

    # devel
    # print("A kernel is now ready.")

    return kernel


async def check_metadata_flow_sensor(meta_data_comment: str) -> dict[str,str]:
    class DecisionResponse(BaseModel):
        # Put in the structure you expect to be return from the kernel
        answer:  str
        comment: str

    kernel = get_kernel()

    # import skill from plugin
    check_meta_data_functions = kernel.import_semantic_plugin_from_directory(plugins_directory, "CheckMetaData")

    # make function available
    check_flow_sensor_function = check_meta_data_functions["FlowSensor"]

    # make decision
    decision = await kernel.run(check_flow_sensor_function, input_str=meta_data_comment)
    #print(decision, type(decision))
    #print('---')

    #print("The meta data of the flow sensor is beeing analyzed by the 'FlowSensor' routine of the CheckMetaData plugin.")

    # convert answer to variable
    # TODO: consider using Pydantic to parse the json
    # https://youtu.be/yj-wSRJwrrc
    # https://youtu.be/_1Nf9KNhsPw

    # try:
    #     decision_model = DecisionResponse.model_validate(decision) # TODO ask: Input should be a valid dictionary or instance of DecisionResponse?
    #     #print(decision_model)
    #     ret = decision_model
    # except ValidationError as e:
    #     print(f"Validation error when parsing decision: {e}")
    #     ret = {"answer": "error", "comment": "Validation error when parsing decision."}

    try:
        ret = json.loads(str(decision))
        # print(json.dumps(ret, indent=2))
    except Exception as e:
        print(f"""Error in check_metadata_flow_sensor: Could not convert "{str(decision)}" to json.""")
        ret={"answer": "error", "comment": "Could not convert to json."}
        # import traceback
        # traceback.print_exc()
    # old, keep for reference
    # decide = kernel.create_semantic_function(prompt, max_tokens=2000, temperature=0.2, top_p=0.5)
    # decision = decide(meta_data_comment) # type: ignore
    # print(decision)

    return ret


# executed when run as script (outside Jupyter)
if __name__ == "__main__":
    print("executing SKtools as script...");
    tic = pendulum.now();
    # test get_meta_data
    meta_data = GetMetaData('bf_f12_47a_zurcherstr', start_date="2020-08-01", end_date="2020-10-01")#f"""clogging of Venturi during this period(measured level true but wrong flow signal!)"""
    for comment in meta_data.comment:

        decision = asyncio.run(check_metadata_flow_sensor(comment))
    
    # print result
    #print(json.dumps(decision, indent=2))
    
    toc = pendulum.now() - tic
    print(f"Wall time: {toc.minutes:02}:{toc.seconds:02}+{toc.microseconds/1000:03}") # type: ignore
    
