from textual import events
from textual.screen import Screen
from textual.widgets import Static
from textual.reactive import reactive

GHOST = """
                                                             ..:::.                                 
                                                     .:::::::      :::::::.                         
                                                 .::::.                  .::::                      
                                               :::                           .:::                   
                                             :::                                :::                 
                                           :::                                    .::               
                                         .::                   :::::::              :::             
                                        .:.                          :::              ::            
                                       .::                        :::: ::              ::           
                                      .::                        ::::::              :::            
                                      ::                         ::::::           :::               
                                     ::                          ::::::         :::                 
                   :::::::::::::::  ::                            ::::       :::                    
                                    ::                                     ::                       
                                    ::                                  :::                         
          ::::::::::::::::::::::   ::                                :::                           
                                   ::                             .:::                              
                                  ::                             ::                                
              ::::::::::::::::    ::      .                        :::                              
                                 ::       :                          :::                            
                                ::       :                              :::                         
                              .::       :                                  :::                      
                             ::.      ::                                     :::.                   
                          .:::      .:.                                         :::                 
                      .::::.      .::                 :                            ::               
              ::::::::.         ::.                  :.                            ::               
               ::.          .::                     :.                            ::                
                .::                                :.                ..          ::                 
                   :::                           ::                  :         .:.                  
                      :::::::::                .:.                 .:         ::.                   
                              ::              ::                  ::        .::                     
                              .:.           ::                   ::        ::.                      
                             .::         ::.                    :.       :::                        
                            ::.                               ::        ::                          
                           ::              .::::::          .:        ::                            
                           ::       ..:::::      ::       .:       .::.                             
                             ::::::::            ::              :::.                               
                                                ::            .:::                                  
                                               ::::::::::::::::                                     
"""

ASCII_HEIGHT = len(GHOST.strip("\n").splitlines())


class SplashScreen(Screen):
    """Center-screen logo while data initialises."""

    FALLBACK_TEXT = "SPECTR"
    message: reactive[str] = reactive("Loading...")

    def compose(self):
        self.logo = Static(id="logo-art", classes="center")
        self.msg = Static(self.message, id="splash-msg", classes="center")
        yield self.logo
        yield self.msg

    def on_mount(self) -> None:
        self._update_logo()
        self.msg.update(self.message)

    def on_resize(self, event: events.Resize) -> None:  # noqa: D401
        self._update_logo()

    def update_message(self, text: str) -> None:
        """Update the message under the logo."""
        self.message = text

    def _update_logo(self) -> None:
        if self.app.size.height < ASCII_HEIGHT:
            self.logo.update(self.FALLBACK_TEXT)
        else:
            self.logo.update(GHOST)

    def watch_message(self, old: str, new: str) -> None:  # type: ignore[override]
        self.msg.update(new)
