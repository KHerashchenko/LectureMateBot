Welcome to 🎓 LectureMate project
==============================================

_Bot for transcribing, summarizing, and chatting about YouTube videos._  
_Link: https://t.me/LectureMate_bot_

This project is a serverless application built on AWS using AWS SAM template. It leverages AWS services such as Lambda functions, API Gateway, and S3 for storage, etc. It integrates with OpenAI API for natural language processing and utilizes Pinecone vector database for efficient similarity search, and utilizes Telegram as the user interface.

__Justification for each resource used in the project:__

- DynamoDB: Chosen for its flexibility over relational databases to accommodate the dynamic nature of user data.
- YouTube Transcript API: Implemented using a Python library, enabling seamless retrieval of video transcriptions for summaries.
- OpenAI API: Utilized to power the chatbot's natural language understanding, enhancing user interactions with the platform, taking advantage of the free tier.
- Telegram Bot: Chosen as the user interface due to its simplicity of built-in user management and platform accessibility.
- AWS Lambda: Utilized for serverless architecture, enabling scalable and cost-efficient execution of functions without the need for server management.
- API Gateway: Facilitates smooth integration between the Telegram bot and the backend Lambda functions, ensuring seamless communication.
- AWS S3: Implemented to store supplementary files and resources,  isolating users' data, and ensuring secure and efficient storage.
- CodeStar: Employed for continuous integration and continuous delivery, streamlining development and ensuring a smooth user experience.
- Pinecone: Leveraged as the vector database to store and process data for efficient AI-powered operations.

AWS CloudWatch: Employed for monitoring and logging, aiding in identifying and addressing potential issues promptly.

GitHub: Used as the version control system to track and manage the codebase, ensuring a collaborative and organized development process.

![new-designer](https://github.com/KHerashchenko/LectureMateBot/assets/43710814/e168efdb-99c4-46ab-b016-9b32a41e32c6)
