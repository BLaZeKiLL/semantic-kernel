# Copyright (c) Microsoft. All rights reserved.

import json
import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, Final, Iterator, List, Optional, Tuple, Type, Union

from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.chat_role import ChatRole
from semantic_kernel.kernel_pydantic import KernelBaseModel

logger = logging.getLogger(__name__)

ROOT_KEY_MESSAGE: Final[str] = "message"


class ChatHistory(KernelBaseModel):
    """
    This class holds the history of chat messages from a chat conversation.

    Note: the constructor takes a system_message parameter, which is not part
    of the class definition. This is to allow the system_message to be passed in
    as a keyword argument, but not be part of the class definition.

    Attributes:
        messages (List[ChatMessageContent]): The list of chat messages in the history.
    """

    messages: List[ChatMessageContent]

    def __init__(self, **data: Any):
        """
        Initializes a new instance of the ChatHistory class, optionally incorporating a message and/or
        a system message at the beginning of the chat history.

        This constructor allows for flexible initialization with chat messages and an optional messages or a
        system message. If both 'messages' (a list of ChatMessageContent instances) and 'system_message' are
        provided, the 'system_message' is prepended to the list of messages, ensuring it appears as the first
        message in the history. If only 'system_message' is provided without any 'messages', the chat history is
        initialized with the 'system_message' as its first item. If 'messages' are provided without a
        'system_message', the chat history is initialized with the provided messages as is.

        Parameters:
        - **data: Arbitrary keyword arguments. The constructor looks for two optional keys:
            - 'messages': Optional[List[ChatMessageContent]], a list of chat messages to include in the history.
            - 'system_message' Optional[str]: An optional string representing a system-generated message to be
                included at the start of the chat history.

        Note: The 'system_message' is not retained as part of the class's attributes; it's used during
        initialization and then discarded. The rest of the keyword arguments are passed to the superclass
        constructor and handled according to the Pydantic model's behavior.
        """
        system_message_content = data.pop("system_message", None)

        if system_message_content:
            system_message = ChatMessageContent(role=ChatRole.SYSTEM, content=system_message_content)

            if "messages" in data:
                data["messages"] = [system_message] + data["messages"]
            else:
                data["messages"] = [system_message]
        if "messages" not in data:
            data["messages"] = []
        super().__init__(**data)

    def add_system_message(self, content: str) -> None:
        """Add a system message to the chat history."""
        self.add_message(message=self._prepare_for_add(ChatRole.SYSTEM, content))

    def add_user_message(self, content: str) -> None:
        """Add a user message to the chat history."""
        self.add_message(message=self._prepare_for_add(ChatRole.USER, content))

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the chat history."""
        self.add_message(message=self._prepare_for_add(ChatRole.ASSISTANT, content))

    def add_tool_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a tool message to the chat history."""
        self.add_message(message=self._prepare_for_add(ChatRole.TOOL, content), metadata=metadata)

    def add_message(
        self,
        message: Union[ChatMessageContent, Dict[str, Any]],
        encoding: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a message to the history.

        This method accepts either a ChatMessageContent instance or a
        dictionary with the necessary information to construct a ChatMessageContent instance.

        Args:
            message (Union[ChatMessageContent, dict]): The message to add, either as
                a pre-constructed ChatMessageContent instance or a dictionary specifying 'role' and 'content'.
            encoding (Optional[str]): The encoding of the message. Required if 'message' is a dict.
            metadata (Optional[dict[str, Any]]): Any metadata to attach to the message. Required if 'message' is a dict.
        """
        if isinstance(message, ChatMessageContent):
            self.messages.append(message)
            return
        if "role" not in message:
            raise ValueError(f"Dictionary must contain at least the role. Got: {message}")
        if encoding:
            message["encoding"] = encoding
        if metadata:
            message["metadata"] = metadata
        self.messages.append(ChatMessageContent(**message))

    def _prepare_for_add(self, role: ChatRole, content: str) -> Dict[str, str]:
        """Prepare a message to be added to the history."""
        return {"role": role, "content": content}

    def remove_message(self, message: ChatMessageContent) -> bool:
        """Remove a message from the history.

        Args:
            message (ChatMessageContent): The message to remove.

        Returns:
            bool: True if the message was removed, False if the message was not found.
        """
        try:
            self.messages.remove(message)
            return True
        except ValueError:
            return False

    def __len__(self) -> int:
        """Return the number of messages in the history."""
        return len(self.messages)

    def __getitem__(self, index: int) -> ChatMessageContent:
        """Get a message from the history using the [] operator.

        Args:
            index (int): The index of the message to get.

        Returns:
            ChatMessageContent: The message at the specified index.
        """
        return self.messages[index]

    def __contains__(self, item: ChatMessageContent) -> bool:
        """Check if a message is in the history.

        Args:
            item (ChatMessageContent): The message to check for.

        Returns:
            bool: True if the message is in the history, False otherwise.
        """
        return item in self.messages

    def __str__(self) -> str:
        """Return a string representation of the history."""
        if not self.messages:
            return ""
        return "\n".join([msg.to_prompt(root_key=ROOT_KEY_MESSAGE) for msg in self.messages])

    def __iter__(self) -> Iterator[ChatMessageContent]:
        """Return an iterator over the messages in the history."""
        return iter(self.messages)

    def __eq__(self, other: "ChatHistory") -> bool:
        """Check if two ChatHistory instances are equal."""
        if not isinstance(other, ChatHistory):
            return False

        return self.messages == other.messages

    @classmethod
    def from_rendered_prompt(
        cls, rendered_prompt: str, chat_message_content_type: Type[ChatMessageContent] = ChatMessageContent
    ) -> "ChatHistory":
        """
        Create a ChatHistory instance from a rendered prompt.

        Args:
            rendered_prompt (str): The rendered prompt to convert to a ChatHistory instance.

        Returns:
            ChatHistory: The ChatHistory instance created from the rendered prompt.
        """
        messages: List[chat_message_content_type] = []
        result, remainder = cls._render_remaining(rendered_prompt, chat_message_content_type, True)
        if result:
            messages.append(result)
        while remainder:
            result, remainder = cls._render_remaining(remainder, chat_message_content_type)
            if result:
                messages.append(result)
        return cls(messages=messages)

    @staticmethod
    def _render_remaining(
        prompt: Optional[str],
        chat_message_content_type: Type[ChatMessageContent] = ChatMessageContent,
        first: bool = False,
    ) -> Tuple[Optional[ChatMessageContent], Optional[str]]:
        """Render the remaining messages in the history."""
        if not prompt:
            return None, None
        prompt = prompt.strip()
        start = prompt.find(f"<{ROOT_KEY_MESSAGE}")
        end_tag = f"</{ROOT_KEY_MESSAGE}>"
        single_item_end_tag = "/>"
        end = prompt.find(end_tag)
        end_of_tag = end + len(end_tag)
        if end == -1:
            end = prompt.find(single_item_end_tag)
            end_of_tag = end + len(single_item_end_tag)
        if start == -1 or end == -1:
            return chat_message_content_type(role=ChatRole.SYSTEM if first else ChatRole.USER, content=prompt), None
        if start > 0 and end > 0:
            return (
                chat_message_content_type(role=ChatRole.SYSTEM if first else ChatRole.USER, content=prompt[:start]),
                prompt[start:],
            )
        try:
            return chat_message_content_type.from_element(ET.fromstring(prompt[start:end_of_tag])), prompt[end_of_tag:]
        except ET.ParseError:
            logger.warning(f"Unable to parse prompt: {prompt[start:end_of_tag]}, returning as content")
            return (
                chat_message_content_type(
                    role=ChatRole.SYSTEM if first else ChatRole.USER, content=prompt[start:end_of_tag]
                ),
                prompt[end_of_tag:],
            )

    def serialize(self) -> str:
        """
        Serializes the ChatHistory instance to a JSON string.

        Returns:
            str: A JSON string representation of the ChatHistory instance.

        Raises:
            ValueError: If the ChatHistory instance cannot be serialized to JSON.
        """
        try:
            return self.model_dump_json(indent=4)
        except TypeError as e:
            raise ValueError(f"Unable to serialize ChatHistory to JSON: {e}")

    @classmethod
    def restore_chat_history(cls, chat_history_json: str) -> "ChatHistory":
        """
        Restores a ChatHistory instance from a JSON string.

        Args:
            chat_history_json (str): The JSON string to deserialize
                into a ChatHistory instance.

        Returns:
            ChatHistory: The deserialized ChatHistory instance.

        Raises:
            ValueError: If the JSON string is invalid or the deserialized data
                fails validation.
        """
        try:
            return ChatHistory.model_validate_json(chat_history_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")

    def store_chat_history_to_file(chat_history: "ChatHistory", file_path: str) -> None:
        """
        Stores the serialized ChatHistory to a file.

        Args:
            chat_history (ChatHistory): The ChatHistory instance to serialize and store.
            file_path (str): The path to the file where the serialized data will be stored.
        """
        json_str = chat_history.serialize()
        with open(file_path, "w") as file:
            file.write(json_str)

    def load_chat_history_from_file(file_path: str) -> "ChatHistory":
        """
        Loads the ChatHistory from a file.

        Args:
            file_path (str): The path to the file from which to load the ChatHistory.

        Returns:
            ChatHistory: The deserialized ChatHistory instance.
        """
        with open(file_path, "r") as file:
            json_str = file.read()
        return ChatHistory.restore_chat_history(json_str)
