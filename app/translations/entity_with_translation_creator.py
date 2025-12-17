from typing import Any, Optional, Type, TypeVar
from fastapi import HTTPException
from sqlmodel import Session

# Type variables
ModelType = TypeVar('ModelType')
TranslationType = TypeVar('TranslationType')
CreateSchemaType = TypeVar('CreateSchemaType')
UpdateSchemaType = TypeVar('UpdateSchemaType')

class EntityWithTranslationsManager:
    """
    Unified manager for creating and updating entities with translations.
    Handles the common CRUD patterns for entities that have translation relationships.
    """
    
    def __init__(self, session: Session, restaurant_id: Optional[int] = None):
        self.session = session
        self.restaurant_id = restaurant_id
    
    def create(
        self,
        create_data: CreateSchemaType,
        main_model: Type[ModelType],
        translation_model: Type[TranslationType],
        foreign_key_field: str
    ) -> ModelType:
        """
        Create a new entity with translations.
        
        Args:
            create_data: Pydantic model with main data and translations
            main_model: SQLAlchemy model class for main entity
            translation_model: SQLAlchemy model class for translations
            foreign_key_field: Name of the foreign key field in translation model
        
        Returns:
            Created main entity with translations
        """
        # Create main entity
        main_data = create_data.model_dump(exclude={'translations'})
        db_entity = main_model.model_validate(main_data)
        
        # Set restaurant_id if provided
        if self.restaurant_id is not None:
            db_entity.restaurant_id = self.restaurant_id
        
        self.session.add(db_entity)
        self.session.commit()
        self.session.refresh(db_entity)

        # Create translations
        if hasattr(create_data, 'translations') and create_data.translations:
            self._create_translations(
                create_data.translations, 
                db_entity.id, 
                translation_model, 
                foreign_key_field
            )
        
        return db_entity
    
    def update(
        self,
        entity_id: int,
        update_data: UpdateSchemaType,
        main_model: Type[ModelType],
        translation_model: Type[TranslationType],
        foreign_key_field: str,
        entity_name: str
    ) -> ModelType:
        """
        Update an existing entity with translations.
        
        Args:
            entity_id: ID of the entity to update
            update_data: Pydantic model with update data and translations
            main_model: SQLAlchemy model class for main entity
            translation_model: SQLAlchemy model class for translations
            foreign_key_field: Name of the foreign key field in translation model
            entity_name: Name of entity for error messages
        
        Returns:
            Updated main entity with translations
            
        Raises:
            HTTPException: If entity not found (404) or update fails (500)
        """
        try:
            print("heeeeere")
            # Get existing entity
            db_entity = self.session.get(main_model, entity_id)

            print("heeeeere")
            if not db_entity:
                raise HTTPException(
                    status_code=404, 
                    detail=f"{entity_name} with ID {entity_id} not found"
                )
            
            # Update main entity
            main_data = update_data.model_dump(exclude_unset=True, exclude={'translations'})

            print("heeeeere")
            if main_data:  # Only update if there's data to update
                try:
                    print("heeeeere")
                    db_entity.sqlmodel_update(main_data)
                    self.session.add(db_entity)
                    self.session.commit()
                    self.session.refresh(db_entity)
                except Exception as e:
                    self.session.rollback()
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to update {entity_name} main data: {str(e)}"
                    )
            
            # Update translations if provided
            if hasattr(update_data, 'translations') and update_data.translations is not None:
                try:
                    print("heeeeere")
                    self._replace_translations(
                        db_entity,
                        update_data.translations,
                        translation_model,
                        foreign_key_field
                    )
                except Exception as e:
                    self.session.rollback()
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to update {entity_name} translations: {str(e)}"
                    )
            
            return db_entity
            
        except HTTPException:
            # Re-raise HTTP exceptions (404, 500) as-is
            # These are already properly formatted with status codes and messages
            raise
            
        except Exception as e:
            # Catch any unexpected errors not handled above
            # This is a safety net for unforeseen issues
            self.session.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error while updating {entity_name}: {type(e).__name__} - {str(e)}"
            )
    
    def _create_translations(
        self, 
        translations: list, 
        entity_id: int, 
        translation_model: Type[TranslationType], 
        foreign_key_field: str
    ) -> None:
        """Helper method to create translations."""
        for translation in translations:
            db_translation = translation_model.model_validate(translation)
            setattr(db_translation, foreign_key_field, entity_id)
            self.session.add(db_translation)
        
        self.session.commit()
        self.session.refresh
    
    def _replace_translations(
        self, 
        db_entity: ModelType, 
        new_translations: list, 
        translation_model: Type[TranslationType], 
        foreign_key_field: str
    ) -> None:
        """Helper method to replace existing translations."""
        # Delete existing translations
        for translation in db_entity.translations:
            self.session.delete(translation)
        
        # Create new translations
        for translation_data in new_translations:
            db_translation = translation_model.model_validate(translation_data)
            setattr(db_translation, foreign_key_field, db_entity.id)
            self.session.add(db_translation)
        
        self.session.commit()
        self.session.refresh(db_entity)

    def get_by_id(
        self, 
        entity_id: int, 
        main_model: Type[ModelType], 
        entity_name: str
    ) -> ModelType:
        """
        Get an entity by ID with proper error handling.
        
        Args:
            entity_id: ID of the entity
            main_model: SQLAlchemy model class
            entity_name: Name of entity for error messages
            
        Returns:
            Entity instance
        """
        db_entity = self.session.get(main_model, entity_id)
        if not db_entity:
            raise HTTPException(status_code=404, detail=f"{entity_name} not found")
        return db_entity