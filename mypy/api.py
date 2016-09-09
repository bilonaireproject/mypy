# This module contains an API for using mypy as a module inside another (host) application,
# rather than from the command line or as a separate process
# Examples of such host applications are IDE's and command line build- or (pre)compilation-tools.
# Once this API is stable and flexible enough, it deserves consideration to make the command line version of mypy just another host application
#
# Being an interface, this module attempts to be thin, stable and self-explanatory
# Since the guts of mypy are bound to change, it doesn't depend too much upon them
# Rather it presents an external view of mypy, using a very limited number of domain bound, hence presumably relativey stable concepts
#
# More specific, it exports:
#
#   -   A singleton object named type_validator, representing mypy to the host application
#       This object features two methods:
#
#       -   Method set_options, which allows setting those options of mypy which are meant for production use
#           Its argument list makes clear which they are and which defaults they have
#
#       -   Method validate, which receives a list of strings, denoting source file paths of top level modules
#           These top level modules and the modules they import are checked recursively
#           Method validate returns a polymorphic list containing objects whose class derives from ValidationError
#
#   -   Class ValidationMessage
#       It facilitates the use of its subclasses in a polymorphic, but still typed, list
#       In most situations there's no need to use this baseclass directly
#       Objects of its subclasses represent messages that the validator wants to deliver to the user via the host
#       Such objects are in binary form, granting the host the freedom to convert them to any suitable format
#
#       -   Class ValidationRemark is a subclass of ValidationMessage
#           It is the baseclass of all ValidationMessage's that do not represent an error
#
#       -   Class ValidationError is the baseclass of all errors encountered during a valiation run
#           In most situations there's no need to use this baseclass directly
#           There is no separate warning class, rather objects of some subclasses of ValidationError can have an error_severity attribute
#
#           -   Class StaticTypingError is a subclass of ValidationError
#               Its instances represent static typing inconsistencies found by mypy
#               Finding objects of this class is what mypy is about
#
#           -   Class CompilationError is a subclass of ValidationError
#               Its instances represent any other problem encountered by mypy
#               Currently this category isn't subdivided any further
#               It's derived classes, which are currently unused, suggest that in the future such a subdivision may be useful
#
#               -   Class SyntaxError is a subclass of CompilationError
#                   Its instances represent syntax errors encountered by mypy in the code under scrutiny
#                   It is there for future use
#                   While in the end the Python interpreter will catch any syntax errors,
#                   if mypy alreay knows about them, a second parse is redundant and can be avoided
#       
#               -   Class InternalError is a subclass of CompilationError
#                   Its instances represent errors due to malfunction of mypy itself
#                   It is there for future use 

import sys
from typing import List
from mypy import build, defaults, errors, options

class ValidationMessage:
# Any message produced by the validator.
# These messages are structured objects rather than strings
# In this way each tool that hosts mypy can represent them in its own suitable text format
    def __init__ (self):
    # Default values of inherited attributes are set here
    # However overriding them happens explicitly in derived classes, rather than via this constructor
        self.identifier = None
        self.description = None

class ValidationRemark (ValidationMessage):
# Any ValidationMessage that isn't a ValidationError
    pass
    
class ValidationError (ValidationMessage):
# Any error produced by the validator
# Having a common (abstract) base class allows the use of polymorphic, yet typed, error lists
    pass
    
class StaticTypingError (ValidationError):
# Any typing inconsistency in the code that is being validated
    def __init__ (self, error_info: errors.ErrorInfo) -> None:
        ValidationError.__init__ (self)     # Make sure all attributes are at least there, but init them explicitly below
    
        self._error_info = error_info       # Internal to mypy, not part of the API
        
        self.description = self._error_info.message
        self.import_context = self._error_info.import_ctx
        self.file_name = self._error_info.file.replace ('\\', '/')
        self.class_name = self._error_info.type
        self.function_name = self._error_info.function_or_member
        self.line_nr = self._error_info.line
        self.severity = self._error_info.severity


class CompilationError (ValidationError):
# Any other error occuring during validation that isn't a StaticTypingError
    def __init__ (self, compile_error: errors.CompileError) -> None:
        ValidationError.__init__ (self)     # Make sure all attributes are at least there, but init them explicitly below
        
        self._compile_error = compile_error                                 # Internal to mypy, not part of the API
        self._static_typing_errors = [] # type: List [StaticTypingError]    # Internal to mypy, not part of the API
        
        # BEGIN tempory hack
        # Since a CompileError doesn't contain raw error info, we'll just reconstruct it from text for now
        # The alternative, adding an attribute containing raw error info to CompileError, is avoided for the moment,
        # since such a temporary solution might easily lead even more code becoming dependent on this vulnerable part of the design 
        # The long term solution is probably a thorough revision of the raise_error / CompileError mechanism,
        # but currently the focus is on getting the external view of this API right
        # Behind such a stable facade all kinds of future reconstruction activities may be endeavoured, limiting their impact on hosts
        
        if self._compile_error.messages [0] .startswith ('mypy:'):
            self.description = self._compile_error.messages [0]
        else:
            self.description = 'Unspecified compilation error'
            
            for formatted_message in self._compile_error.messages:
                if ': error:' in formatted_message:
                    file_name, line_nr, severity, description = formatted_message.split (':', 4)
                    self._static_typing_errors.append (StaticTypingError (errors.ErrorInfo (
                        import_ctx = None,
                        file = file_name,
                        typ = None,
                        function_or_member = None,
                        line = line_nr,
                        severity = severity,
                        message = description,
                        blocker = None,
                        only_once = None
                    )))
                    
        # END temporary hack        
        
class SyntaxError (CompilationError):
# For future use
    pass
    
class InternalError (CompilationError):
# For future use
    pass
                    
class _TypeValidator:
# Private class, only a singleton instance is exported
    def __init__ (self) -> None:
        self.set_options ()
    
    def set_options (
        self,
        python_version = defaults.PYTHON3_VERSION,  # Target Python version 
        platform = sys.platform,                    # Target platform
        silent_imports = False,                     # Only import types from .pyi files, not from .py files             
        disallow_untyped_calls = False,             # Disallow calling untyped functions from typed ones
        disallow_untyped_defs = False,              # Disallow defining untyped (or incompletely typed) functions
        check_untyped_defs = False,                 # Type check unannotated functions
        warn_incomplete_stub = False,               # Also check typeshed for missing annotations
        warn_redundant_casts = False,               # Warn about casting an expression to its inferred type
        warn_unused_ignores = False                 # Warn about unused '# type: ignore' comments
    ) -> None:
        params = locals () .items ()
        self._options = options.Options ()
        for param in params:
            setattr (self._options, *param)
        
    def validate (self, source_paths: str) -> List [ValidationMessage]:
    # A call to validate denotes one validation run on a list of top level modules and the hierarchy of modules they import recursively
    # This method returns one polymorphic list of ValidationMessage's, enabling easy future expansion and refinement of the message hierarchy
        compilation_error = None
        
        try:
            build_result = build.build (
                [build.BuildSource (source_path, None, None) for source_path in source_paths],
                self._options
            )
            static_typing_errors = [StaticTypingError (error_info) for error_info in build_result.manager.errors.error_info]
        except errors.CompileError as compile_error:
            compilation_error = CompilationError (compile_error)
            static_typing_errors = compilation_error._static_typing_errors
            
        validation_messages = [] # type: List [ValidationMessage]
            
        # Sort StaticTypingError's on file_name, line_nr, error_message respectively, then remove duplicates
        old_error = None # type: StaticTypingError
        for index, error in enumerate (sorted (
            static_typing_errors,
            key = lambda error: (error.file_name, error.line_nr, error.description)
        )):
            if (index and (not (
                error._error_info.only_once and 
                error.file_name == old_error.file_name and
                error.line_nr == old_error.line_nr and
                error.description == old_error.description
            ))):
                validation_messages.append (error)
                old_error = error

        # Append instance of CompilationError if it's there
        if compilation_error:
            validation_messages.append (compilation_error)
            
        return validation_messages


type_validator = _TypeValidator ()
# Singleton instance, exported to represent the mypy static type validator in any 3rd party tools that it's part of

# (Module revision timestamp: y16m09d09 h9m55s00 GMT)
